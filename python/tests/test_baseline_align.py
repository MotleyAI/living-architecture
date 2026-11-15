"""Python refactors keep `.basedpyright/baseline.json` aligned, with the real basedpyright as the configured checker."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from project_files import file_tree, write_project
from refactor_cli import BIN_DIR, configure_typecheck, line_col, read, run

from living_architecture.contract import message
from living_architecture.refactor import baseline_align

BASELINE = ".basedpyright/baseline.json"
USE = """\
class Store:
    def get_model(self, name: str) -> int:
        return len(name)


def takes_str(x: str) -> None:
    print(x)


def use(s: Store) -> None:
    print(s.get_model("a"), takes_str(1))
    print(s.get_model("b"), takes_str(2))
    y: str = (
        s.get_model("c"))
    print(y, takes_str(3))
"""


def _entry(code: str, start: int, end: int, lines: int = 1) -> dict[str, object]:
    return {"code": code, "range": {"startColumn": start, "endColumn": end, "lineCount": lines}}


ARG = "reportArgumentType"
ASSIGN = "reportAssignmentType"
DEPRECATED = "reportDeprecated"


@pytest.fixture
def checker_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", f"{BIN_DIR}{os.pathsep}{os.environ['PATH']}")


def _typecheck(root: Path, *argv: str) -> tuple[int, str]:
    """`la-typecheck` in `root`, as a process (the checker writes to the inherited stdout)."""
    env = {**os.environ, "PATH": f"{BIN_DIR}{os.pathsep}{os.environ['PATH']}"}
    proc = subprocess.run([str(BIN_DIR / "la-typecheck"), *argv], cwd=root, env=env, capture_output=True, text=True,
                          check=False)
    return proc.returncode, proc.stdout


def _project(
    tmp_path: Path,
    files: dict[str, str],
    command: str | None = "basedpyright",
    name: str = "proj",
) -> Path:
    """A git repo with `files`, `command` as the Python checker and a baseline written from the files."""
    root = write_project(tmp_path / name, files)
    configure_typecheck(root, "basedpyright")
    assert _typecheck(root, "--write-baseline")[0] == 0
    configure_typecheck(root, command)
    return root


def _entries(root: Path, rel: str) -> list[dict[str, object]]:
    return json.loads(read(root, BASELINE))["files"][f"./{rel}"]


def _rename(root: Path, needle: str, new_name: str, *, apply: bool = True, rel: str = "pkg/use.py") -> list[str]:
    return [*(["--apply"] if apply else []), "rename", "--file", rel, *line_col(root, rel, needle), "--new-name",
            new_name]


@pytest.mark.usefixtures("checker_path")
@pytest.mark.parametrize("command", ["basedpyright", "basedpyright -p .", "basedpyright pkg"],
                         ids=["plain", "project-flag", "positional-path"])
def test_rename_shifts_baselined_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], command: str
) -> None:
    root = _project(tmp_path, {"pkg/use.py": USE}, command)
    before = _entries(root, "pkg/use.py")
    code, _out, err = run(root, _rename(root, "get_model", "load"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    after = _entries(root, "pkg/use.py")
    assert before[:3] == [_entry(ARG, 38, 39), _entry(ARG, 38, 39), _entry(ASSIGN, 13, 25, 2)]
    assert after == [_entry(ARG, 33, 34), _entry(ARG, 33, 34), _entry(ASSIGN, 13, 20, 2), before[3]]
    assert _typecheck(root)[0] == 0


@pytest.mark.usefixtures("checker_path")
def test_dry_run_shows_the_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dry = _project(tmp_path, {"pkg/use.py": USE}, name="dry")
    applied = _project(tmp_path, {"pkg/use.py": USE}, name="applied")
    before = file_tree(dry)
    code, out, _err = run(dry, _rename(dry, "get_model", "load", apply=False), monkeypatch, capsys)
    assert code == 0
    assert f"--- a/{BASELINE}\n+++ b/{BASELINE}\n" in out
    assert message("refactor.dry-run", count=2) in out
    assert file_tree(dry) == before
    applied_out = run(applied, _rename(applied, "get_model", "load"), monkeypatch, capsys)[1]
    footer = message("refactor.applied", count=2).lstrip("\n")
    assert applied_out.split(footer)[0] == out.split(message("refactor.dry-run", count=2).lstrip("\n"))[0]


STOLEN = '    print("ABCDEFGHIJKLMN", takes_str(0))\n'


def _new_error_rows(output: str) -> list[str]:
    """`path:line - error ... (rule)` rows of a checker run, without the column."""
    rows = []
    for row in output.splitlines():
        if " - error:" in row:
            location, rest = row.strip().split(" - ", 1)
            rows.append(f"{location.rsplit(':', 1)[0]} {rest}")
    return rows


@pytest.mark.usefixtures("checker_path")
def test_matching_follows_basedpyright(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {"pkg/use.py": USE})
    stale = _entry("reportCallIssue", 4, 9)
    baseline = json.loads(read(root, BASELINE))
    baseline["files"]["./pkg/use.py"].append(stale)
    (root / BASELINE).write_text(json.dumps(baseline, indent=4), encoding="utf-8")
    (root / "pkg/use.py").write_text(USE.replace("def use(s: Store) -> None:\n", "def use(s: Store) -> None:\n" + STOLEN),
                                     encoding="utf-8")
    copy = tmp_path / "copy"
    shutil.copytree(root, copy)
    expected_rows = _new_error_rows(_typecheck(copy)[1].replace(str(copy), str(root)))
    assert len(expected_rows) == 1

    code, _out, err = run(root, _rename(root, "get_model", "load"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert _entries(root, "pkg/use.py") == [
        _entry(ARG, 38, 39), _entry(ARG, 33, 34), _entry(ASSIGN, 13, 20, 2), _entry(ARG, 23, 24), stale,
    ]
    code, output = _typecheck(root)
    assert code == 1
    assert _new_error_rows(output) == expected_rows


EDGES = """\
from typing_extensions import deprecated


@deprecated("use load")
def get_model() -> int:
    return 1


def use() -> None:
    get_model()
    x: str = (
        get_model())
    print(x)
"""


@pytest.mark.usefixtures("checker_path")
def test_ranges_at_and_around_the_renamed_span(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {"pkg/edges.py": EDGES})
    before = _entries(root, "pkg/edges.py")
    assert before == [
        _entry("reportUnusedCallResult", 4, 15), _entry(DEPRECATED, 4, 13), _entry(ASSIGN, 13, 20, 2),
        _entry(DEPRECATED, 8, 17),
    ]
    code, _out, err = run(root, _rename(root, "get_model", "load", rel="pkg/edges.py"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert _entries(root, "pkg/edges.py") == [
        _entry("reportUnusedCallResult", 4, 10), _entry(DEPRECATED, 4, 8), _entry(ASSIGN, 13, 15, 2),
        _entry(DEPRECATED, 8, 12),
    ]
    assert _typecheck(root)[0] == 0


@pytest.mark.usefixtures("checker_path")
def test_moved_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = _project(tmp_path, {"pkg/a.py": USE, "pkg/sub/__init__.py": "", "pkg/b.py": "from pkg.a import Store\n"})
    entries = _entries(root, "pkg/a.py")
    code, _out, err = run(root, ["--apply", "move-module", "--module", "pkg/a.py", "--dest", "pkg/sub"], monkeypatch,
                          capsys)
    assert (code, err) == (0, "")
    files = json.loads(read(root, BASELINE))["files"]
    assert "./pkg/a.py" not in files
    assert files["./pkg/sub/a.py"] == entries
    assert _typecheck(root)[0] == 0


SOURCE = """\
def keep() -> int:
    return 1


def moved(x: int) -> str:
    return x
"""
DEST = 'y: int = "first"\n'


@pytest.mark.usefixtures("checker_path")
def test_moved_declaration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = _project(tmp_path, {"pkg/source.py": SOURCE, "pkg/dest.py": DEST})
    moved_entry = _entries(root, "pkg/source.py")[-1]
    dest_entries = _entries(root, "pkg/dest.py")
    argv = ["--apply", "move-symbol", "--file", "pkg/source.py", *line_col(root, "pkg/source.py", "moved"), "--dest",
            "pkg/dest.py"]
    code, _out, err = run(root, argv, monkeypatch, capsys)
    assert (code, err) == (0, "")
    files = json.loads(read(root, BASELINE))["files"]
    assert read(root, "pkg/dest.py").startswith("def moved(")  # rope puts it above the first statement
    assert files["./pkg/dest.py"] == [moved_entry, *dest_entries]
    assert moved_entry not in files.get("./pkg/source.py", [])
    assert _typecheck(root)[0] == 0


@pytest.mark.usefixtures("checker_path")
@pytest.mark.parametrize("variant", ["no-baseline", "null-command"])
def test_no_alignment_without_a_baseline_or_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], variant: str
) -> None:
    plain = write_project(tmp_path / "plain", {"pkg/use.py": USE})
    expected = run(plain, _rename(plain, "get_model", "load"), monkeypatch, capsys)
    if variant == "no-baseline":
        root = write_project(tmp_path / "proj", {"pkg/use.py": USE})
        configure_typecheck(root, "/nonexistent/basedpyright")
    else:
        root = _project(tmp_path, {"pkg/use.py": USE}, command=None)
    baseline = file_tree(root).get(BASELINE)
    assert run(root, _rename(root, "get_model", "load"), monkeypatch, capsys) == expected
    assert file_tree(root).get(BASELINE) == baseline
    assert read(root, "pkg/use.py") == read(plain, "pkg/use.py")
    _assert_symbol_locator_too(root, monkeypatch, capsys)


def _assert_symbol_locator_too(root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """The same rename back by `--symbol` also runs without a checker."""
    argv = ["--apply", "rename", "--file", "pkg/use.py", "--symbol", "Store.load", "--new-name", "get_model"]
    code, _out, err = run(root, argv, monkeypatch, capsys)
    assert (code, err) == (0, "")


@pytest.mark.usefixtures("checker_path")
def test_checker_failure_refuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = _project(tmp_path, {"pkg/use.py": USE}, command="/nonexistent/basedpyright")
    before = file_tree(root)
    expected = message("refactor.baseline-failed", language="python")
    assert run(root, _rename(root, "get_model", "load"), monkeypatch, capsys) == (1, "", f"{expected}\n")
    assert file_tree(root) == before


@pytest.mark.usefixtures("checker_path")
def test_warnings_print_when_the_baseline_stays_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {"pkg/use.py": USE})
    before = read(root, BASELINE)
    monkeypatch.setattr(baseline_align, "_follow", lambda *_args: None)
    code, _out, err = run(root, _rename(root, "get_model", "load"), monkeypatch, capsys)
    expected = {message("refactor.baseline-ambiguous", baseline=BASELINE, code=c, path="pkg/use.py") for c in (ARG, ASSIGN)}
    assert (code, set(err.splitlines())) == (0, expected)
    assert read(root, BASELINE) == before
