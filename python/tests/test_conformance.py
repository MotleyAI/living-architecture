"""Conformance runner: every case under conformance/cases reproduces its goldens byte-for-byte.

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
from pathlib import Path

import pytest
import yaml

from living_architecture import __version__
from living_architecture.contract import contract_hash


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "conformance" / "cases").is_dir():
            return candidate
    raise RuntimeError("conformance/cases not found above the tests directory")


REPO_ROOT = _repo_root()
CORPUS = REPO_ROOT / "conformance"
CASES = sorted(p.parent for p in (CORPUS / "cases").glob("*/case.yaml"))
UPDATE = os.environ.get("LA_UPDATE_GOLDENS") == "1"
TWIN = os.environ.get("LA_CONFORMANCE_TWIN", "python")
CROSS = os.environ.get("LA_CONFORMANCE_CROSS") == "1"
BIN_DIRS = {"python": Path(sys.executable).parent}
if os.environ.get("LA_NODE_BIN_DIR"):
    BIN_DIRS["typescript"] = Path(os.environ["LA_NODE_BIN_DIR"])
OVERLAY_DIRS = {"python": "python", "typescript": "node"}
MANIFEST = yaml.safe_load((REPO_ROOT / "shared" / "cli.yaml").read_text(encoding="utf-8"))["commands"]
# Never reachable from a case unless it provides them: the host's own la tools and the twins' runners.
_ALWAYS_HIDDEN = {*MANIFEST, "npx", "uvx"}
FIXED_DATE = "2026-01-01T00:00:00+00:00"
_COMMAND_PREFIXES = {"arch", "config", "doctor", "conventions", "count", "compliance", "mock", "refactor", "shim", "twin"}

FAKE_GH = """\
import json, os, subprocess, sys

argv = sys.argv[1:]
with open(os.environ["FAKE_GH_ROUTES"]) as fh:
    routes = json.load(fh)
for route in routes:
    if all(tok in argv for tok in route["match"]):
        out = route.get("stdout", "")
        for flag in ("--jq", "-q"):
            if flag in argv:
                jq = subprocess.run(["jq", "-rc", argv[argv.index(flag) + 1]], input=out,
                                    capture_output=True, text=True, check=False)
                sys.stderr.write(jq.stderr)
                out = jq.stdout
        sys.stdout.write(out)
        sys.exit(route.get("exit", 0))
sys.stderr.write("fake gh: no route for " + " ".join(argv) + "\\n")
sys.exit(1)
"""


class CaseResult:
    def __init__(self, exit_code: int, stdout: str, stderr: str, files: dict[str, str]) -> None:
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.files = files


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
    return MANIFEST[command].get("native")


def selected(case: dict, variant: Variant, twin: str, *, cross: bool) -> bool:
    """Whether `twin`'s run includes this variant: pinned cases run only through their twin."""
    pinned = case.get("twin")
    if pinned is not None:
        return pinned == twin
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


def _apply_step(step: dict, *, repo: Path, root: Path, env: dict[str, str]) -> None:
    [(op, arg)] = step.items()
    if op == "write":
        _write_files(repo, arg)
    elif op == "commit":
        _git(repo, env, "add", "-A")
        _git(repo, env, "commit", "-q", "-m", arg)
    elif op == "branch":
        _git(repo, env, "checkout", "-q", "-b", arg)
    elif op == "checkout":
        _git(repo, env, "checkout", "-q", arg)
    elif op == "stage":
        _git(repo, env, "add", "--", *arg)
    elif op == "delete":
        for rel in arg:
            (repo / rel).unlink()
    elif op == "git_rm":
        _git(repo, env, "rm", "-q", "--", *arg)
    elif op == "rename":
        for src, dst in arg.items():
            _git(repo, env, "mv", src, dst)
    elif op == "origin":
        origin = root / "origin.git"
        if not origin.exists():
            subprocess.run(["git", "init", "-q", "--bare", str(origin)], env=env, check=True, capture_output=True)
            _git(repo, env, "remote", "add", "origin", str(origin))
        _git(repo, env, "push", "-q", "origin", *arg)
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


def substitute(text: str, root: Path) -> str:
    """Placeholders allowed in args and fake executables."""
    return text.replace("<VERSION>", __version__).replace("<CONTRACT_HASH>", contract_hash()).replace("<ROOT>", str(root))


def _fake_bins(root: Path, case: dict) -> tuple[list[str], list[str]]:
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
            path.write_text(substitute(text, root), encoding="utf-8")
            path.chmod(0o644 if name in spec.get("nonexec", []) else 0o755)
        placed[spec.get("position", "after")].append(str(directory))
    return placed["before"], placed["after"]


def _twin_dirs(case: dict, twin: str) -> list[str]:
    """The invoking twin's bin dir first, then the other twin's when known and not hidden by the case."""
    dirs = [str(BIN_DIRS[twin])]
    if case.get("other_twin") != "absent":
        dirs += [str(path) for language, path in BIN_DIRS.items() if language != twin]
    return dirs


def _environment(root: Path, case: dict, twin: str) -> dict[str, str]:
    home = root / "home"
    home.mkdir()
    (home / ".gitconfig").write_text("", encoding="utf-8")
    (root / "tmp").mkdir()
    fake_bin = root / "fakebin"
    fake_bin.mkdir()
    hidden = case.get("hide", [])
    if "gh" not in hidden:
        gh = fake_bin / "gh"
        gh.write_text(f"#!{sys.executable}\n{FAKE_GH}", encoding="utf-8")
        gh.chmod(0o755)
    routes = [
        {"match": r["match"], "stdout": r["stdout"] if isinstance(r.get("stdout"), str) else json.dumps(r.get("stdout", "")),
         "exit": r.get("exit", 0)}
        for r in case.get("gh", [])
    ]
    (root / "gh-routes.json").write_text(json.dumps(routes), encoding="utf-8")
    before, after = _fake_bins(root, case)
    tools = _tools_dir(frozenset({*hidden, *_ALWAYS_HIDDEN}))
    env = {
        "PATH": os.pathsep.join([str(fake_bin), *before, *_twin_dirs(case, twin), *after, str(tools)]),
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
    }
    env.update({k: substitute(str(v), root) for k, v in case.get("env", {}).items()})
    return env


def materialize(
    case_dir: Path, case: dict, root: Path, variant: Variant, twin: str = TWIN
) -> tuple[Path, dict[str, str]]:
    """Build the case's repo under `root`; returns (repo dir, subprocess env)."""
    repo = root / "repo"
    repo.mkdir(parents=True)
    for overlay in _overlays(case_dir, case, variant):
        _copy_tree(overlay, repo)
    for rel in case.get("remove", []):
        target = repo / rel
        shutil.rmtree(target) if target.is_dir() and not target.is_symlink() else target.unlink()
    for link, target in case.get("symlinks", {}).items():
        (repo / link).parent.mkdir(parents=True, exist_ok=True)
        (repo / link).symlink_to(target)
    env = _environment(root, case, twin)
    git = case.get("git", [])
    if git != "none":
        _git(repo, env, "init", "-q", "-b", "main")
        for step in git:
            _apply_step(step, repo=repo, root=root, env=env)
    return repo, env


def _normalize(text: str, root: Path, case: dict) -> str:
    for form in {str(root.resolve()), str(root)}:
        text = text.replace(form, "<ROOT>")
    for rule in case.get("normalize", []):
        if rule == "version":
            text = text.replace(__version__, "<VERSION>")
        elif rule == "contract_hash":
            text = text.replace(contract_hash(), "<CONTRACT_HASH>")
        else:
            text = re.sub(rule["pattern"], rule["replace"], text)
    return text


def run_case(case_dir: Path, root: Path, variant: Variant = NEUTRAL, twin: str = TWIN) -> CaseResult:
    case = load_case(case_dir)
    repo, env = materialize(case_dir, case, root, variant, twin)
    command = BIN_DIRS[twin] / case["command"]
    if not command.is_file():
        raise FileNotFoundError(f"command {case['command']} is not installed in {BIN_DIRS[twin]}")
    proc = subprocess.run(
        [str(command), *[substitute(str(a), root) for a in case.get("args", [])]],
        cwd=repo / case.get("cwd", "."),
        env=env,
        input=case.get("stdin", "").encode("utf-8"),
        capture_output=True,
        timeout=120,
        check=False,
    )
    files = {
        rel: _normalize((repo / rel).read_bytes().decode("utf-8"), root, case) if (repo / rel).is_file() else "<MISSING>\n"
        for rel in case.get("expect", {}).get("files", [])
    }
    return CaseResult(
        exit_code=proc.returncode,
        stdout=_normalize(proc.stdout.decode("utf-8"), root, case),
        stderr=_normalize(proc.stderr.decode("utf-8"), root, case),
        files=files,
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


def _check_stream(case_dir: Path, mode: object, stream: str, actual: str, golden: str | None, *, update: bool) -> list[str]:
    if mode == "ignore":
        return []
    if isinstance(mode, dict):
        return [f"{stream} lacks {needle!r}:\n{actual}" for needle in mode["contains"] if needle not in actual]
    path = _golden_path(case_dir, stream, golden)
    if mode == "json":
        return _check_json(path, actual)
    if update:
        path.write_bytes(actual.encode("utf-8"))
        return []
    if not path.exists():
        return [f"missing golden {path.name}; generate it with LA_UPDATE_GOLDENS=1"]
    expected = path.read_bytes().decode("utf-8")
    return [] if expected == actual else [_diff(expected, actual, stream)]


def _pretty(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _check_json(path: Path, actual: str) -> list[str]:
    """One JSON document equal to the golden's as a value (array order counts, formatting does not).

    `<VERSION>` and `<CONTRACT_HASH>` in the golden stand for the installed values.
    """
    try:
        document = json.loads(actual)
    except json.JSONDecodeError as exc:
        return [f"stdout is not one JSON document: {exc}\n{actual}"]
    golden = path.read_text(encoding="utf-8").replace("<VERSION>", __version__)
    expected = json.loads(golden.replace("<CONTRACT_HASH>", contract_hash()))
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
    problems = _check_stream(case_dir, expect.get("stdout"), "stdout", result.stdout, variant.golden, update=write)
    problems += _check_stream(case_dir, expect.get("stderr"), "stderr", result.stderr, variant.golden, update=write)
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


def _selected_runs() -> list[object]:
    runs = []
    for case_dir in CASES:
        case = load_case(case_dir)
        for variant in variants(case):
            if selected(case, variant, TWIN, cross=CROSS):
                runs.append(pytest.param(case_dir, variant, id=f"{case_dir.name}[{variant.id}]"))
    return runs


@pytest.mark.parametrize(("case_dir", "variant"), _selected_runs())
def test_case(case_dir: Path, variant: Variant, tmp_path: Path) -> None:
    problems = check_case(case_dir, tmp_path, update=UPDATE, variant=variant)
    assert not problems, "\n".join(problems)


def test_corpus_is_not_empty() -> None:
    assert len(CASES) > 100


@pytest.mark.parametrize("case_dir", CASES, ids=lambda p: p.name)
def test_case_declares_kind_and_exit(case_dir: Path) -> None:
    case = load_case(case_dir)
    assert case["kind"] in ("neutral", "paired", "adapter")
    assert case["kind"] == "neutral" or case["languages"]
    assert isinstance(case["expect"]["exit"], int)


def test_inventory_lists_exactly_the_cases() -> None:
    listed = set(re.findall(r"`([a-z0-9-]+)`", (CORPUS / "INVENTORY.md").read_text(encoding="utf-8")))
    cases = {c.name for c in CASES}
    assert cases - listed == set(), "cases missing from INVENTORY.md"
    assert {name for name in listed if name.split("-")[0] in _COMMAND_PREFIXES} - cases == set()


def test_no_corpus_file_is_git_ignored() -> None:
    """An ignored fixture passes locally but is never committed, so the case breaks in CI."""
    out = subprocess.run(
        ["git", "ls-files", "--others", "--ignored", "--exclude-standard", "--", "conformance"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout
    assert out.splitlines() == []



def _wrong_golden_case(tmp_path: Path) -> Path:
    case_dir = tmp_path / "cases" / "wrong"
    case_dir.mkdir(parents=True)
    (case_dir / "case.yaml").write_text(
        "kind: neutral\ncommand: la-config\nargs: [get, issue_key_pattern]\nexpect: {exit: 0}\n", encoding="utf-8"
    )
    (case_dir / "stdout").write_text("not the real output\n", encoding="utf-8")
    (case_dir / "stderr").write_text("", encoding="utf-8")
    return case_dir


def test_wrong_golden_fails_with_a_diff_and_stays_untouched(tmp_path: Path) -> None:
    case_dir = _wrong_golden_case(tmp_path)
    problems = check_case(case_dir, tmp_path / "run")
    assert "-not the real output" in "\n".join(problems)
    assert (case_dir / "stdout").read_text(encoding="utf-8") == "not the real output\n"


def test_update_mode_rewrites_the_golden(tmp_path: Path) -> None:
    case_dir = _wrong_golden_case(tmp_path)
    assert check_case(case_dir, tmp_path / "run", update=True) == []
    assert (case_dir / "stdout").read_text(encoding="utf-8") == "[A-Z][A-Z0-9]+-\\d+\n"


def test_update_mode_refuses_an_unexpected_exit(tmp_path: Path) -> None:
    case_dir = _wrong_golden_case(tmp_path)
    (case_dir / "case.yaml").write_text(
        "kind: neutral\ncommand: la-config\nargs: [get, nope]\nexpect: {exit: 0}\n", encoding="utf-8"
    )
    assert check_case(case_dir, tmp_path / "run", update=True)
    assert (case_dir / "stdout").read_text(encoding="utf-8") == "not the real output\n"


# ---- case model


def _case(**fields: object) -> dict:
    return {"kind": "neutral", "command": "la-arch-check", "expect": {"exit": 0}, **fields}


def test_paired_case_runs_once_per_language_with_its_own_overlay() -> None:
    runs = variants(_case(kind="paired", languages=["python", "typescript"]))
    assert [(v.fixture_languages, v.golden) for v in runs] == [(["python"], "python"), (["typescript"], "typescript")]


def test_neutral_case_applies_every_listed_overlay() -> None:
    [variant] = variants(_case(languages=["python", "typescript"]))
    assert (variant.fixture_languages, variant.golden) == (["python", "typescript"], None)


def test_native_selection_needs_own_fixture_languages() -> None:
    case = _case(languages=["python", "typescript"])
    [variant] = variants(case)
    assert not selected(case, variant, "python", cross=False)
    assert selected(case, variant, "python", cross=True)


def test_language_free_case_is_native_to_both_twins() -> None:
    case = _case(command="la-config")
    assert selected(case, NEUTRAL, "python", cross=False)
    assert selected(case, NEUTRAL, "typescript", cross=False)


def test_python_only_command_is_not_native_to_the_npm_twin() -> None:
    case = _case(command="la-check-conventions")
    assert selected(case, NEUTRAL, "python", cross=False)
    assert not selected(case, NEUTRAL, "typescript", cross=False)


def test_pinned_case_runs_only_through_its_twin() -> None:
    case = _case(twin="typescript", command="la-check-conventions")
    assert selected(case, NEUTRAL, "typescript", cross=False)
    assert not selected(case, NEUTRAL, "python", cross=True)


def test_later_overlay_overwrites_an_earlier_one(tmp_path: Path) -> None:
    case_dir = tmp_path / "cases" / "both"
    for sub, text in (("python", "py\n"), ("node", "ts\n")):
        (case_dir / sub).mkdir(parents=True)
        (case_dir / sub / "shared.txt").write_text(text, encoding="utf-8")
    case = _case(languages=["python", "typescript"], git="none")
    [variant] = variants(case)
    repo, _ = materialize(case_dir, case, tmp_path / "run", variant)
    assert (repo / "shared.txt").read_text(encoding="utf-8") == "ts\n"


@pytest.mark.parametrize("case_dir", CASES, ids=lambda p: p.name)
def test_case_overlays_belong_to_listed_languages(case_dir: Path) -> None:
    case = load_case(case_dir)
    listed = {OVERLAY_DIRS[language] for language in case.get("languages", [])}
    present = {sub for sub in OVERLAY_DIRS.values() if (case_dir / sub).is_dir()}
    assert present <= listed
    assert case.get("twin") in (None, "python", "typescript")


def test_json_stream_ignores_formatting_but_not_array_order(tmp_path: Path) -> None:
    golden = tmp_path / "stdout"
    golden.write_text('{"a": [1, 2], "b": null, "v": "<VERSION>"}\n', encoding="utf-8")
    assert _check_json(golden, json.dumps({"b": None, "a": [1, 2], "v": __version__})) == []
    assert _check_json(golden, '{"a": [2, 1], "b": null}')
    assert _check_json(golden, '{"a": [1, 2]} trailing')
