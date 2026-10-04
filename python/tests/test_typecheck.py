"""la-typecheck: command splitting, exit combination and which languages apply."""

import subprocess
from pathlib import Path

import pytest
import yaml

from living_architecture import cli, typecheck

VECTORS = next(p for p in Path(__file__).resolve().parents if (p / "shared" / "vectors").is_dir()) / "shared" / "vectors"
SPLITS = yaml.safe_load((VECTORS / "command-split.yaml").read_text(encoding="utf-8"))["cases"]
FAKE_CHECKER = '#!/bin/sh\necho "$*" >> checker.log\necho "0 errors, 0 warnings, 0 notes"\nexit {code}\n'


@pytest.mark.parametrize("vector", SPLITS, ids=lambda v: v["name"])
def test_split_command(vector: dict) -> None:
    if vector.get("error"):
        with pytest.raises(ValueError):
            typecheck.split_command(vector["text"])
    else:
        assert typecheck.split_command(vector["text"]) == vector["words"]


@pytest.mark.parametrize(("codes", "expected"), [([], 0), ([0], 0), ([0, 1], 1), ([1, 0], 1), ([2, 1], 2), ([0, 2], 2)])
def test_combined_exit_is_the_highest(codes: list[int], expected: int) -> None:
    assert typecheck.combined_exit(codes) == expected


def _repo(root: Path, files: dict[str, str], *, checker_exit: int = 0, git: bool = True) -> Path:
    if git:
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    fake = root / ".venv" / "bin" / "basedpyright"
    fake.parent.mkdir(parents=True)
    fake.write_text(FAKE_CHECKER.format(code=checker_exit), encoding="utf-8")
    fake.chmod(0o755)
    return root


def _checker_calls(root: Path) -> list[str]:
    log = root / "checker.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


@pytest.fixture
def run(monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]):
    def go(root: Path, *argv: str) -> tuple[int, str, str]:
        monkeypatch.chdir(root)
        code = cli.la_typecheck(list(argv))
        out, err = capfd.readouterr()
        return code, out, err

    return go


def test_stray_script_checks_only_python(tmp_path: Path, run) -> None:
    root = _repo(tmp_path, {"pyproject.toml": "", "a.py": "X = 1\n", "docs/static/app.js": "x;\n"})
    code, out, err = run(root)
    assert (code, _checker_calls(root)) == (0, [""])
    assert "checking python with basedpyright" in err
    assert "typescript" not in err + out


def test_explicit_entry_without_markers(tmp_path: Path, run) -> None:
    config = "commands: {typecheck: {python: basedpyright -p python}}\n"
    root = _repo(tmp_path, {"living-architecture.yaml": config, "python/a.py": "X = 1\n"})
    assert run(root)[0] == 0
    assert _checker_calls(root) == ["-p python"]


def test_null_turns_a_language_off(tmp_path: Path, run) -> None:
    config = "commands: {typecheck: {python: null}}\n"
    root = _repo(tmp_path, {"living-architecture.yaml": config, "pyproject.toml": "", "a.py": "X = 1\n"})
    code, _, err = run(root)
    assert (code, _checker_calls(root)) == (0, [])
    assert "nothing to check" in err


def test_no_applicable_language(tmp_path: Path, run) -> None:
    root = _repo(tmp_path, {"README.md": "x\n", "a.py": "X = 1\n"})
    code, _, err = run(root)
    assert (code, _checker_calls(root)) == (0, [])
    assert "nothing to check" in err


def test_not_a_git_repo(tmp_path: Path, run) -> None:
    root = _repo(tmp_path, {"pyproject.toml": "", "a.py": "X = 1\n"}, git=False)
    code, _, err = run(root)
    assert (code, _checker_calls(root)) == (2, [])
    assert "not inside a git repository" in err


@pytest.mark.parametrize(("checker_exit", "expected"), [(0, 0), (1, 1), (2, 2), (3, 2)])
def test_python_exit_codes(tmp_path: Path, run, checker_exit: int, expected: int) -> None:
    root = _repo(tmp_path, {"pyproject.toml": "", "a.py": "X = 1\n"}, checker_exit=checker_exit)
    assert run(root)[0] == expected


@pytest.mark.parametrize("checker_exit", [0, 1])
def test_write_baseline_appends_the_flag_and_exits_0(tmp_path: Path, run, checker_exit: int) -> None:
    root = _repo(tmp_path, {"pyproject.toml": "", "a.py": "X = 1\n"}, checker_exit=checker_exit)
    assert run(root, "--write-baseline")[0] == 0
    assert _checker_calls(root) == ["--writebaseline"]


def test_write_baseline_skips_an_existing_baseline(tmp_path: Path, run) -> None:
    files = {"pyproject.toml": "", "a.py": "X = 1\n", ".basedpyright/baseline.json": '{"files": {}}\n'}
    root = _repo(tmp_path, files)
    code, _, err = run(root, "--write-baseline")
    assert (code, _checker_calls(root)) == (2, [])
    assert ".basedpyright/baseline.json exists, skipped" in err
