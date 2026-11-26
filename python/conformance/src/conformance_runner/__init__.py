"""Conformance runner: every case under conformance/<package>/cases reproduces its goldens byte-for-byte.

`LA_UPDATE_GOLDENS=1` writes goldens; a normal run only diffs. Case format: conformance/README.md.
`LA_CONFORMANCE_TWIN` (python | typescript) picks the invoking twin, `LA_NODE_BIN_DIR` holds the npm twin's
commands, and `LA_CONFORMANCE_CROSS=1` runs every case instead of the twin's native ones.
"""

from __future__ import annotations

import atexit
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Collection
from pathlib import Path
from typing import Any

import yaml

from conformance_runner import fake_gh_cli
from living_architecture import __version__
from living_architecture.contract import contract_hash as la_contract_hash
from trmv import __version__ as trmv_version
from trmv.contract import config_files, config_formats, language
from trmv.contract import contract_hash as trmv_contract_hash


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "conformance" / "fixtures").is_dir():
            return candidate
    raise RuntimeError("conformance/fixtures not found above the runner")


REPO_ROOT = _repo_root()
CORPUS = REPO_ROOT / "conformance"
PACKAGES = ("trmv", "la")
CASES = sorted((p.parent for package in PACKAGES for p in (CORPUS / package / "cases").glob("*/case.yaml")),
               key=lambda case_dir: case_dir.name)
UPDATE = os.environ.get("LA_UPDATE_GOLDENS") == "1"
TWIN = os.environ.get("LA_CONFORMANCE_TWIN", "python")
CROSS = os.environ.get("LA_CONFORMANCE_CROSS") == "1"
BIN_DIRS = {"python": Path(sys.executable).parent}
if os.environ.get("LA_NODE_BIN_DIR"):
    BIN_DIRS["typescript"] = Path(os.environ["LA_NODE_BIN_DIR"])
OVERLAY_DIRS = {"python": "python", "typescript": "node"}
MANIFESTS = {
    package: yaml.safe_load((REPO_ROOT / "shared" / package / "cli.yaml").read_text(encoding="utf-8"))["commands"]
    for package in PACKAGES
}
MANIFEST = {name: spec for commands in MANIFESTS.values() for name, spec in commands.items()}
# Never reachable from a case unless it provides them: the host's own la tools and the twins' runners.
_ALWAYS_HIDDEN = {*MANIFEST, "npx", "uvx"}
FIXED_DATE = "2026-01-01T00:00:00+00:00"
VERSION_PLACEHOLDER = "<VERSION>"
CONTRACT_HASH_PLACEHOLDER = "<CONTRACT_HASH>"
TRMV_CONTRACT_HASH_PLACEHOLDER = "<TRMV_CONTRACT_HASH>"
COMMAND_PREFIXES = {
    "affected", "arch", "config", "doctor", "conventions", "count", "compliance", "mock", "refactor", "shim", "twin",
    "typecheck",
}

class CaseResult:
    def __init__(self, exit_code: int, stdout: str, stderr: str, files: dict[str, str], git_status: str | None = None) -> None:
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.files = files
        self.git_status = git_status


class Variant:
    """One run of a case: the fixture languages whose overlays apply, and the golden suffix (paired/adapter)."""

    def __init__(self, fixture_languages: list[str], golden: str | None) -> None:
        self.fixture_languages = fixture_languages
        self.golden = golden

    @property
    def id(self) -> str:
        return self.golden or "neutral"


NEUTRAL = Variant([], None)


def load_case(case_dir: Path) -> dict:
    return yaml.safe_load((case_dir / "case.yaml").read_text(encoding="utf-8"))


def variants(case: dict) -> list[Variant]:
    languages = case.get("languages", [])
    if case["kind"] == "paired":
        return [Variant([language], language) for language in languages]
    if case["kind"] == "adapter":
        return [Variant(languages, languages[0])]
    return [Variant(languages, None)]


def native_languages(command: str) -> list[str] | None:
    """The languages whose twin runs `command` natively; None for a neutral command."""
    return MANIFEST.get(command, {}).get("native")


def selected(case: dict, variant: Variant, twin: str, *, cross: bool, bins: Collection[str] = BIN_DIRS.keys()) -> bool:
    """Whether `twin`'s run includes this variant: pinned cases run only through their twin, and only when every
    language's twin among `bins` unless the other twin is kept off PATH."""
    pinned = case.get("twin")
    if pinned is not None:
        reachable = case.get("other_twin") == "absent" or set(variant.fixture_languages) <= {twin, *bins}
        return pinned == twin and reachable
    if cross:
        return True
    native = native_languages(case["command"])
    return set(variant.fixture_languages) <= {twin} and (native is None or twin in native)


def _copy_tree(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=True)


def _overlays(case_dir: Path, case: dict, variant: Variant) -> list[Path]:
    bases = []
    if case.get("fixture"):
        bases.append(CORPUS / "fixtures" / case["fixture"])
    bases.append(case_dir)
    subs = ["repo", *(OVERLAY_DIRS[language] for language in variant.fixture_languages)]
    return [base / sub for base in bases for sub in subs]


def _git(repo: Path, env: dict[str, str], *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)


def _write_files(repo: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))


# Per git step taking its argument as-is: the git arguments it runs.
_GIT_STEPS: dict[str, Callable[[Any], list[str]]] = {
    "branch": lambda arg: ["checkout", "-q", "-b", arg],
    "checkout": lambda arg: ["checkout", "-q", arg],
    "orphan": lambda arg: ["checkout", "-q", "--orphan", arg],
    "stage": lambda arg: ["add", "--", *arg],
    "git_rm": lambda arg: ["rm", "-q", "--", *arg],
}


def _push_origin(repo: Path, root: Path, env: dict[str, str], refs: list[str]) -> None:
    origin = root / "origin.git"
    if not origin.exists():
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], env=env, check=True, capture_output=True)
        _git(repo, env, "remote", "add", "origin", str(origin))
    _git(repo, env, "push", "-q", "origin", *refs)


def _apply_step(step: dict, *, repo: Path, root: Path, env: dict[str, str], package: str = "la") -> None:
    [(op, arg)] = step.items()
    if op in _GIT_STEPS:
        _git(repo, env, *_GIT_STEPS[op](arg))
    elif op == "write":
        _write_files(repo, {rel: with_format(substitute(text, root, package)) for rel, text in arg.items()})
    elif op == "commit":
        _git(repo, env, "add", "-A")
        _git(repo, env, "commit", "-q", "-m", arg)
    elif op == "delete":
        for rel in arg:
            (repo / rel).unlink()
    elif op == "rename":
        for src, dst in arg.items():
            _git(repo, env, "mv", src, dst)
    elif op == "origin":
        _push_origin(repo, root, env, arg)
    else:
        raise ValueError(f"unknown git step {op!r}")


_TOOLS_DIRS: dict[frozenset[str], Path] = {}


def _tools_dir(hidden: frozenset[str]) -> Path:
    """The host PATH's executables minus `hidden`, mirrored once per session into one directory."""
    if hidden not in _TOOLS_DIRS:
        tools = Path(tempfile.mkdtemp(prefix="la-conformance-tools-"))
        atexit.register(shutil.rmtree, tools, True)
        for directory in os.environ["PATH"].split(os.pathsep):
            if not Path(directory).is_dir():
                continue
            for entry in Path(directory).iterdir():
                target = tools / entry.name
                if entry.name not in hidden and not target.exists() and os.access(entry, os.X_OK):
                    target.symlink_to(entry)
        _TOOLS_DIRS[hidden] = tools
    return _TOOLS_DIRS[hidden]


def contract_hash(package: str) -> str:
    """The contract hash of `package`'s bundled snapshot."""
    return la_contract_hash() if package == "la" else trmv_contract_hash()


def version(package: str) -> str:
    """The installed version of `package`."""
    return __version__ if package == "la" else trmv_version


def substitute(text: str, root: Path, package: str = "la") -> str:
    """Placeholders allowed in args and fake executables; `<VERSION>` and `<CONTRACT_HASH>` are the case's package's."""
    major, minor = version(package).split(".")[:2]
    text = _installed(text, package).replace("<MAJOR>", major).replace("<MINOR>", minor)
    return text.replace("<ROOT>", str(root))


def _installed(text: str, package: str) -> str:
    """`text` with the version and contract hash placeholders replaced by `package`'s installed values."""
    text = text.replace(VERSION_PLACEHOLDER, version(package))
    text = text.replace(TRMV_CONTRACT_HASH_PLACEHOLDER, trmv_contract_hash())
    return text.replace(CONTRACT_HASH_PLACEHOLDER, contract_hash(package))


def current_format() -> str:
    """The format of living-architecture.yaml the bundled contracts read and write."""
    return config_formats(config_files()[-1])[-1]


def _file_format(name: str) -> str:
    """The current format of committed config file `name`."""
    return current_format() if name == config_files()[-1] else config_formats(name)[-1]


def with_format(text: str) -> str:
    """`<FORMAT>` replaced by the current format; read only when the placeholder occurs."""
    return text.replace("<FORMAT>", current_format()) if "<FORMAT>" in text else text


def _per_language(value: list | dict, variant: Variant) -> list:
    """`value`, or a paired case's entry for the variant's language when it is keyed by language."""
    if isinstance(value, dict):
        [language] = variant.fixture_languages
        return value[language]
    return value


def case_args(case: dict, variant: Variant) -> list[str]:
    """The case's args; a paired case may key them by language."""
    return [str(a) for a in _per_language(case.get("args", []), variant)]


def case_files(case: dict, variant: Variant) -> list[str]:
    """The files the case compares with `files/`; a paired case may key them by language."""
    return [str(f) for f in _per_language(case.get("expect", {}).get("files", []), variant)]


def _substitute_config_files(repo: Path, case: dict, variant: Variant) -> None:
    """`<FORMAT>` in the committed config at the repo root and at the root a case passes with `--root`."""
    args = case_args(case, variant)
    roots = [repo, *([repo / args[args.index("--root") + 1]] if "--root" in args[:-1] else [])]
    for root in roots:
        for name in config_files():
            path = root / name
            if path.is_file() and not path.is_symlink() and b"<FORMAT>" in (data := path.read_bytes()):
                path.write_bytes(data.replace(b"<FORMAT>", _file_format(name).encode("utf-8")))


def _fake_bins(root: Path, case: dict, package: str) -> tuple[list[str], list[str]]:
    """The case's fake executable dirs placed (before, after) the twins' bin dirs."""
    placed: dict[str, list[str]] = {"before": [], "after": []}
    for spec in case.get("bins", []):
        directory = root / "bins" / spec["dir"]
        if "link" in spec:
            directory.parent.mkdir(parents=True, exist_ok=True)
            directory.symlink_to(root / "bins" / spec["link"], target_is_directory=True)
        else:
            directory.mkdir(parents=True)
        for name, text in spec.get("files", {}).items():
            path = directory / name
            path.write_text(substitute(text, root, package), encoding="utf-8")
            path.chmod(0o644 if name in spec.get("nonexec", []) else 0o755)
        placed[spec.get("position", "after")].append(str(directory))
    return placed["before"], placed["after"]


def _without(directory: Path, hidden: set[str], root: Path) -> Path:
    """`directory`, or a mirror of it under `root` without the `hidden` commands it holds."""
    if not any((directory / name).exists() for name in hidden):
        return directory
    mirror = root / "twinbin" / directory.name
    mirror.mkdir(parents=True, exist_ok=True)
    for entry in directory.iterdir():
        if entry.name not in hidden:
            (mirror / entry.name).symlink_to(entry)
    return mirror


def _twin_dirs(case: dict, twin: str, root: Path) -> list[str]:
    """The invoking twin's bin dir first, then the other twin's when known and not hidden by the case; commands the
    case hides are left out of both."""
    hidden = set(case.get("hide", []))
    dirs = [BIN_DIRS[twin]]
    if case.get("other_twin") != "absent":
        dirs += [path for language, path in BIN_DIRS.items() if language != twin]
    return [str(_without(path, hidden, root)) for path in dirs]


def _environment(root: Path, case: dict, twin: str, package: str) -> dict[str, str]:
    home = root / "home"
    home.mkdir()
    (home / ".gitconfig").write_text("", encoding="utf-8")
    (root / "tmp").mkdir()
    fake_bin = root / "fakebin"
    fake_bin.mkdir()
    hidden = case.get("hide", [])
    if "gh" not in hidden:
        fake_gh_cli.install(fake_bin)
    fake_gh_cli.write_routes(root / "gh-routes.json", case.get("gh", []))
    before, after = _fake_bins(root, case, package)
    tools = _tools_dir(frozenset({*hidden, *_ALWAYS_HIDDEN}))
    cache = root / "cache"
    cache.mkdir()
    env = {
        "PATH": os.pathsep.join([str(fake_bin), *before, *_twin_dirs(case, twin, root), *after, str(tools)]),
        "HOME": str(home),
        "TMPDIR": str(root / "tmp"),
        "LC_ALL": "C",
        "TZ": "UTC",
        "COLUMNS": "80",
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"),
        "GIT_AUTHOR_NAME": "Conformance",
        "GIT_AUTHOR_EMAIL": "conformance@example.invalid",
        "GIT_COMMITTER_NAME": "Conformance",
        "GIT_COMMITTER_EMAIL": "conformance@example.invalid",
        "GIT_AUTHOR_DATE": FIXED_DATE,
        "GIT_COMMITTER_DATE": FIXED_DATE,
        "GIT_ALLOW_PROTOCOL": "file",
        "http_proxy": "http://127.0.0.1:9",
        "https_proxy": "http://127.0.0.1:9",
        "FAKE_GH_ROUTES": str(root / "gh-routes.json"),
        language("python")["cache_dir_variable"]: str(cache),
    }
    env.update({k: substitute(str(v), root, package) for k, v in case.get("env", {}).items()})
    return env


def materialize(
    case_dir: Path, case: dict, root: Path, variant: Variant, twin: str = TWIN
) -> tuple[Path, dict[str, str]]:
    """Build the case's repo under `root`; returns (repo dir, subprocess env)."""
    repo = root / "repo"
    repo.mkdir(parents=True)
    for overlay in _overlays(case_dir, case, variant):
        _copy_tree(overlay, repo)
    _substitute_config_files(repo, case, variant)
    for rel in case.get("remove", []):
        target = repo / rel
        shutil.rmtree(target) if target.is_dir() and not target.is_symlink() else target.unlink()
    for link, target in case.get("symlinks", {}).items():
        (repo / link).parent.mkdir(parents=True, exist_ok=True)
        (repo / link).symlink_to(target)
    package = package_of(case_dir)
    env = _environment(root, case, twin, package)
    git = case.get("git", [])
    if git != "none":
        _git(repo, env, "init", "-q", "-b", "main")
        for step in git:
            _apply_step(step, repo=repo, root=root, env=env, package=package)
    for rel, mode in case.get("chmod", {}).items():
        (repo / rel).chmod(int(mode, 8))
    return repo, env


def _normalize(text: str, root: Path, case: dict, package: str) -> str:
    for form in {str(root.resolve()), str(root)}:
        text = text.replace(form, "<ROOT>")
    for rule in case.get("normalize", []):
        if rule == "version":
            text = text.replace(version(package), VERSION_PLACEHOLDER)
        elif rule == "contract_hash":
            text = text.replace(contract_hash(package), CONTRACT_HASH_PLACEHOLDER)
        elif rule == "trmv_contract_hash":
            text = text.replace(trmv_contract_hash(), TRMV_CONTRACT_HASH_PLACEHOLDER)
        else:
            text = re.sub(rule["pattern"], rule["replace"], text)
    return text


def run_case(case_dir: Path, root: Path, variant: Variant = NEUTRAL, twin: str = TWIN) -> CaseResult:
    case = load_case(case_dir)
    package = package_of(case_dir)
    if case["command"] not in MANIFESTS[package]:
        raise ValueError(f"{case_dir.name}: {case['command']} is not a {package} command")
    repo, env = materialize(case_dir, case, root, variant, twin)
    command = BIN_DIRS[twin] / case["command"]
    if not command.is_file():
        raise FileNotFoundError(f"command {case['command']} is not installed in {BIN_DIRS[twin]}")
    proc = subprocess.run(
        [str(command), *[substitute(a, root, package) for a in case_args(case, variant)]],
        cwd=repo / case.get("cwd", "."),
        env=env,
        input=case.get("stdin", "").encode("utf-8"),
        capture_output=True,
        timeout=120,
        check=False,
    )
    files = {
        rel: _normalize((repo / rel).read_bytes().decode("utf-8"), root, case, package) if (repo / rel).is_file() else "<MISSING>\n"
        for rel in case_files(case, variant)
    }
    status = None
    if case.get("expect", {}).get("git_status"):
        listed = subprocess.run(["git", "status", "--porcelain"], cwd=repo, env=env, capture_output=True, check=True)
        status = _normalize(listed.stdout.decode("utf-8"), root, case, package)
    for rel in case.get("chmod", {}):
        (repo / rel).chmod(0o755)
    return CaseResult(
        exit_code=proc.returncode,
        stdout=_normalize(proc.stdout.decode("utf-8"), root, case, package),
        stderr=_normalize(proc.stderr.decode("utf-8"), root, case, package),
        files=files,
        git_status=status,
    )


def _golden_path(case_dir: Path, stream: str, golden: str | None) -> Path:
    specific = case_dir / f"{stream}.{golden}"
    return specific if golden is not None and specific.exists() else case_dir / stream


def _diff(expected: str, actual: str, label: str) -> str:
    return "".join(
        difflib.unified_diff(
            expected.splitlines(keepends=True), actual.splitlines(keepends=True), f"golden {label}", f"actual {label}"
        )
    )


def _check_stream(
    case_dir: Path, mode: object, stream: str, actual: str, golden: str | None, *, update: bool, package: str = "la"
) -> list[str]:
    if mode == "ignore":
        return []
    if isinstance(mode, dict):
        return [f"{stream} lacks {needle!r}:\n{actual}" for needle in mode["contains"] if needle not in actual]
    path = _golden_path(case_dir, stream, golden)
    if mode == "json":
        return check_json(path, actual, package)
    if update:
        path.write_bytes(actual.encode("utf-8"))
        return []
    if not path.exists():
        return [f"missing golden {path.name}; generate it with LA_UPDATE_GOLDENS=1"]
    expected = path.read_bytes().decode("utf-8")
    return [] if expected == actual else [_diff(expected, actual, stream)]


def _pretty(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def check_json(path: Path, actual: str, package: str = "la") -> list[str]:
    """One JSON document equal to the golden's as a value (array order counts, formatting does not).

    `<VERSION>` and `<CONTRACT_HASH>` in the golden stand for the installed values.
    """
    try:
        document = json.loads(actual)
    except json.JSONDecodeError as exc:
        return [f"stdout is not one JSON document: {exc}\n{actual}"]
    expected = json.loads(_installed(path.read_text(encoding="utf-8"), package))
    if document == expected:
        return []
    return [_diff(_pretty(expected), _pretty(document), "stdout (json)")]


def check_case(
    case_dir: Path, root: Path, *, update: bool = False, variant: Variant = NEUTRAL, twin: str = TWIN
) -> list[str]:
    """Problems with the case's output versus its goldens; in update mode, writes goldens instead."""
    case = load_case(case_dir)
    result = run_case(case_dir, root, variant, twin)
    expect = case["expect"]
    if result.exit_code != expect["exit"]:
        return [f"exit {result.exit_code}, expected {expect['exit']}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"]
    write = update and case.get("golden") != "manual"
    package = package_of(case_dir)
    problems = _check_stream(
        case_dir, expect.get("stdout"), "stdout", result.stdout, variant.golden, update=write, package=package
    )
    problems += _check_stream(
        case_dir, expect.get("stderr"), "stderr", result.stderr, variant.golden, update=write, package=package
    )
    if result.git_status is not None:
        problems += _check_stream(case_dir, None, "git-status", result.git_status, variant.golden, update=write)
    for rel, content in result.files.items():
        golden = case_dir / "files" / rel
        if write:
            golden.parent.mkdir(parents=True, exist_ok=True)
            golden.write_bytes(content.encode("utf-8"))
        elif not golden.exists():
            problems.append(f"missing file golden files/{rel}")
        elif golden.read_bytes().decode("utf-8") != content:
            problems.append(_diff(golden.read_bytes().decode("utf-8"), content, f"files/{rel}"))
    return problems


def package_of(case_dir: Path) -> str:
    """The package of the tree holding the case: `trmv` or `la`."""
    return case_dir.parent.parent.name


def package_cases(package: str) -> list[Path]:
    """The case directories of `package`'s tree, in name order."""
    return sorted(p.parent for p in (CORPUS / package / "cases").glob("*/case.yaml"))


def selected_runs(cases: list[Path]) -> list[tuple[Path, Variant, str]]:
    """The (case, variant, id) runs of `cases` that this twin's run includes."""
    runs = []
    for case_dir in cases:
        case = load_case(case_dir)
        for variant in variants(case):
            if selected(case, variant, TWIN, cross=CROSS):
                runs.append((case_dir, variant, f"{case_dir.name}[{variant.id}]"))
    return runs
