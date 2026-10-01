"""Conformance runner: every case under conformance/cases reproduces its goldens byte-for-byte.

`LA_UPDATE_GOLDENS=1` writes goldens; a normal run only diffs. Case format: conformance/README.md.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from living_architecture import __version__


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "conformance" / "cases").is_dir():
            return candidate
    raise RuntimeError("conformance/cases not found above the tests directory")


REPO_ROOT = _repo_root()
CORPUS = REPO_ROOT / "conformance"
CASES = sorted(p.parent for p in (CORPUS / "cases").glob("*/case.yaml"))
LANGUAGE = "python"
UPDATE = os.environ.get("LA_UPDATE_GOLDENS") == "1"
BIN_DIR = Path(sys.executable).parent
FIXED_DATE = "2026-01-01T00:00:00+00:00"
_COMMAND_PREFIXES = {"arch", "config", "doctor", "conventions", "count", "compliance", "mock", "refactor", "shim"}

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


def load_case(case_dir: Path) -> dict:
    return yaml.safe_load((case_dir / "case.yaml").read_text(encoding="utf-8"))


def applies(case: dict, language: str) -> bool:
    if case["kind"] == "neutral":
        return True
    return language in case["languages"]


def _copy_tree(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=True)


def _overlays(case_dir: Path, case: dict, language: str) -> list[Path]:
    bases = []
    if case.get("fixture"):
        bases.append(CORPUS / "fixtures" / case["fixture"])
    bases.append(case_dir)
    return [base / sub for base in bases for sub in ("repo", language)]


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


def _tools_path(root: Path, hidden: list[str]) -> str:
    """The host PATH, minus `hidden` executables (mirrored into a filtered bin dir)."""
    host = os.environ["PATH"]
    if not hidden:
        return host
    tools = root / "tools"
    tools.mkdir()
    for directory in host.split(os.pathsep):
        if not Path(directory).is_dir():
            continue
        for entry in Path(directory).iterdir():
            target = tools / entry.name
            if entry.name not in hidden and not target.exists() and os.access(entry, os.X_OK):
                target.symlink_to(entry)
    return str(tools)


def _environment(root: Path, case: dict) -> dict[str, str]:
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
    env = {
        "PATH": os.pathsep.join([str(fake_bin), _tools_path(root, hidden)]),
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
    env.update({k: str(v) for k, v in case.get("env", {}).items()})
    return env


def materialize(case_dir: Path, case: dict, root: Path, language: str) -> tuple[Path, dict[str, str]]:
    """Build the case's repo under `root`; returns (repo dir, subprocess env)."""
    repo = root / "repo"
    repo.mkdir(parents=True)
    for overlay in _overlays(case_dir, case, language):
        _copy_tree(overlay, repo)
    for rel in case.get("remove", []):
        target = repo / rel
        shutil.rmtree(target) if target.is_dir() and not target.is_symlink() else target.unlink()
    for link, target in case.get("symlinks", {}).items():
        (repo / link).parent.mkdir(parents=True, exist_ok=True)
        (repo / link).symlink_to(target)
    env = _environment(root, case)
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
        else:
            text = re.sub(rule["pattern"], rule["replace"], text)
    return text


def run_case(case_dir: Path, root: Path, language: str = LANGUAGE) -> CaseResult:
    case = load_case(case_dir)
    repo, env = materialize(case_dir, case, root, language)
    command = BIN_DIR / case["command"]
    if not command.is_file():
        raise FileNotFoundError(f"command {case['command']} is not installed in {BIN_DIR}")
    proc = subprocess.run(
        [str(command), *[str(a).replace("<VERSION>", __version__) for a in case.get("args", [])]],
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


def _golden_path(case_dir: Path, stream: str, language: str) -> Path:
    specific = case_dir / f"{stream}.{language}"
    return specific if specific.exists() else case_dir / stream


def _diff(expected: str, actual: str, label: str) -> str:
    return "".join(
        difflib.unified_diff(
            expected.splitlines(keepends=True), actual.splitlines(keepends=True), f"golden {label}", f"actual {label}"
        )
    )


def _check_stream(case_dir: Path, mode: object, stream: str, actual: str, language: str, *, update: bool) -> list[str]:
    if mode == "ignore":
        return []
    if isinstance(mode, dict):
        return [f"{stream} lacks {needle!r}:\n{actual}" for needle in mode["contains"] if needle not in actual]
    path = _golden_path(case_dir, stream, language)
    if update:
        path.write_bytes(actual.encode("utf-8"))
        return []
    if not path.exists():
        return [f"missing golden {path.name}; generate it with LA_UPDATE_GOLDENS=1"]
    expected = path.read_bytes().decode("utf-8")
    return [] if expected == actual else [_diff(expected, actual, stream)]


def check_case(case_dir: Path, root: Path, *, update: bool = False, language: str = LANGUAGE) -> list[str]:
    """Problems with the case's output versus its goldens; in update mode, writes goldens instead."""
    case = load_case(case_dir)
    result = run_case(case_dir, root, language)
    expect = case["expect"]
    if result.exit_code != expect["exit"]:
        return [f"exit {result.exit_code}, expected {expect['exit']}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"]
    write = update and case.get("golden") != "manual"
    problems = _check_stream(case_dir, expect.get("stdout"), "stdout", result.stdout, language, update=write)
    problems += _check_stream(case_dir, expect.get("stderr"), "stderr", result.stderr, language, update=write)
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


@pytest.mark.parametrize("case_dir", [c for c in CASES if applies(load_case(c), LANGUAGE)], ids=lambda p: p.name)
def test_case(case_dir: Path, tmp_path: Path) -> None:
    problems = check_case(case_dir, tmp_path, update=UPDATE)
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
