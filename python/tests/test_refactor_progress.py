"""`dr-refactor` phases: the map loader's every invalid entry, the keep text check, and the `checks` refusals no
corpus case can reach (walker gaps, a language server that cannot start or answers an error)."""

import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from project_files import file_tree, write_project
from refactor_cli import run_raw

from living_architecture.contract import message
from living_architecture.lang import language_server
from living_architecture.refactor.map_file import MapError, load_map
from living_architecture.refactor.sites import spelled_lines

FAKE_LSP = Path(__file__).with_name("fake_lsp_server.py")
CHECKS = "[resolve]\n[checks]\n"
FOO = "def foo() -> int:\n    return 1\n"
RENAME_FOO = ["rename", "--file", "pkg/a.py", "--symbol", "foo", "--new-name", "bar"]


# ---- the map loader


def test_the_map_loader_names_every_invalid_entry(tmp_path: Path) -> None:
    path = tmp_path / "map.yaml"
    path.write_text(
        "- {file: a.py, symbol: f, new_name: g}\n- {file: a.py, symbol: f}\n"
        "- {file: a.py, symbol: h, new_name: i}\n- {file: a.py, new_name: j}\n",
        encoding="utf-8",
    )
    raw, project = str(path), str(tmp_path)
    with pytest.raises(MapError) as raised:
        load_map(raw, project)
    assert str(raised.value) == "\n".join(
        message("refactor.map-invalid", map=str(path), index=index) for index in (2, 4)
    )


# ---- the keep text check


@pytest.mark.parametrize(
    ("text", "lines"),
    [
        ("a = 1\nb = load()\n", {2}),
        ("x = 1\n", set()),
        ('n = "lo\\x61d"\n', {1}),
        ('x = ("lo"\n     "ad")\n', {1}),
        ("ｌoad = 1\n", {1}),
        ("# load the store\n", {1}),
    ],
    ids=["as-written", "absent", "string-escape", "implicit-concatenation", "nfkc", "comment"],
)
def test_spelled_lines(text: str, lines: set[int]) -> None:
    assert spelled_lines(text, {"load"}) == lines


# ---- keeps the check passes or skips


def test_a_keep_on_a_line_holding_only_the_retarget_target_passes_the_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {
        "pkg/api.py": "def modern() -> int:\n    return 1\n\n\nlegacy = modern\n",
        "pkg/use.py": "from pkg.api import legacy, modern\n\nx = modern()\ny = legacy()\n",
    })
    argv = ["retarget", "--file", "pkg/api.py", "--symbol", "legacy", "--target", "modern", "--keep", "pkg/use.py:3"]
    code, out, err = run_raw(root, argv, monkeypatch, capsys)
    assert (code, out) == (2, "")
    assert "[references 1/1] entry 1: legacy -> modern" in err.splitlines()
    assert err.splitlines()[-1] == message("refactor.keep-unmatched", site="pkg/use.py:3")


def test_the_keep_text_check_is_skipped_when_an_unresolved_entry_spells_no_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {
        "pkg/a.py": FOO,
        "README.md": "# Nothing here\n",
        "map.yaml": "- {file: pkg/a.py, symbol: foo, new_name: bar}\n- {file: pkg/a.py, line: 99, new_name: baz}\n",
    })
    code, out, err = run_raw(root, ["rename-map", "map.yaml", "--keep", "README.md"], monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert err == CHECKS + message("refactor.line-out-of-range", line=99, count=2) + "\n"


def test_a_keep_on_the_renamed_module_file_passes_the_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/a.py": "X = 1\n", "pkg/use.py": "from . import a\n\nprint(a.X)\n"})
    argv = ["--apply", "rename", "--file", "pkg/use.py", "--line", "1", "--col", "15", "--new-name", "b",
            "--keep", "pkg/a.py"]
    code, _out, err = run_raw(root, argv, monkeypatch, capsys)
    assert (code, err) == (0, CHECKS + "[references]\n[write]\n")
    assert (root / "pkg" / "a.py").exists()


def test_a_module_rename_onto_a_taken_name_reports_no_unchecked_keep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/a.py": "X = 1\n", "pkg/b.py": "Y = 2\n",
                                          "pkg/use.py": "from . import a\n\nprint(a.X)\n"})
    argv = ["rename", "--file", "pkg/use.py", "--line", "1", "--col", "15", "--new-name", "b", "--keep", "pkg/use.py"]
    code, out, err = run_raw(root, argv, monkeypatch, capsys)
    conflict = message("refactor.name-conflict", name="b", path="pkg/b.py", line=1)
    assert (code, out, err) == (1, "", CHECKS + "[references]\n" + conflict + "\n")


# ---- refusals in checks


def test_walker_gaps_in_every_entry_module_refuse_in_the_checks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    restore_rope_visitor: Callable[[str], None],
    annotation_gap: str,
) -> None:
    restore_rope_visitor("_arg")
    shifted = annotation_gap.replace("\n\n", "\n" * 7, 1)
    entries = "".join(f"- {{file: pkg/{name}.py, symbol: foo, new_name: bar}}\n" for name in ("g1", "g2"))
    root = write_project(tmp_path / "p", {"pkg/a.py": FOO, "pkg/g2.py": annotation_gap, "pkg/g1.py": shifted,
                                          "map.yaml": entries})
    before = file_tree(root)
    code, out, err = run_raw(root, ["--apply", "rename-map", "map.yaml"], monkeypatch, capsys)
    gaps = [message("refactor.rope-walk", path=f"pkg/{name}.py", line=line) for name, line in (("g1", 8), ("g2", 3))]
    assert (code, out, err) == (1, "", CHECKS + "".join(f"{gap}\n" for gap in gaps))
    assert file_tree(root) == before


@pytest.mark.parametrize("taken", ["", "\n\ndef bar() -> int:\n    return 3\n"], ids=["free", "new-name-taken"])
def test_a_gap_rope_meets_in_the_rules_refuses_only_its_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    restore_rope_visitor: Callable[[str], None],
    annotation_gap: str,
    taken: str,
) -> None:
    # The checker cannot resolve scripts/'s import, so rope walks scripts/use.py only in the rules, after the entry's
    # edit in pkg/a.py; the refused entry's edits then check no name.
    restore_rope_visitor("_arg")
    entries = "- {file: pkg/a.py, symbol: foo, new_name: bar}\n- {file: pkg/a.py, symbol: baz, new_name: qux}\n"
    root = write_project(tmp_path / "p", {
        "pyrightconfig.json": '{"executionEnvironments": [{"root": "scripts"}]}\n',
        "pkg/a.py": FOO + "\n\ndef baz() -> int:\n    return 2\n" + taken,
        "scripts/use.py": annotation_gap,
        "map.yaml": entries,
    })
    before = file_tree(root)
    code, out, err = run_raw(root, ["--apply", "rename-map", "map.yaml"], monkeypatch, capsys)
    entry = {"phase": "rules", "count": 2}
    refused = message("refactor.progress-refused", **entry, n=1, entries=message("refactor.progress-entry", index=1),
                      old="foo", new="bar", refusals=1)
    clean = message("refactor.progress-clean", **entry, n=2, entries=message("refactor.progress-entry", index=2),
                    old="baz", new="qux")
    gap = message("refactor.rope-walk", path="scripts/use.py", line=3)
    assert (code, out) == (1, "")
    assert err.splitlines()[-4:] == [refused, gap, clean, gap]
    assert file_tree(root) == before


def test_a_language_server_that_cannot_start_refuses_with_its_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = str(tmp_path / "no-such-node")
    monkeypatch.setattr(language_server, "_bundled_command", lambda: [missing, "--stdio"])
    root = write_project(tmp_path / "p", {"pkg/a.py": FOO})
    before = file_tree(root)
    code, out, err = run_raw(root, ["--apply", *RENAME_FOO], monkeypatch, capsys)
    error = f"{missing}: no such file or directory"
    cause = message("refactor.checker-not-started", error=error)
    assert (code, out, err) == (1, "", CHECKS + message("refactor.pyright-failed") + "\n" + cause + "\n")
    assert file_tree(root) == before


def test_a_language_server_that_cannot_start_is_reported_when_no_entry_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = str(tmp_path / "no-such-node")
    monkeypatch.setattr(language_server, "_bundled_command", lambda: [missing, "--stdio"])
    root = write_project(tmp_path / "p", {"pkg/a.py": FOO})
    code, out, err = run_raw(root, ["rename", "--file", "pkg/a.py", "--line", "99", "--new-name", "bar"], monkeypatch,
                             capsys)
    error = f"{missing}: no such file or directory"
    expected = [message("refactor.line-out-of-range", line=99, count=2), message("refactor.pyright-failed"),
                message("refactor.checker-not-started", error=error)]
    assert (code, out, err) == (1, "", CHECKS + "".join(f"{line}\n" for line in expected))


def test_a_language_server_answering_an_error_refuses_with_its_answer_and_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    record = tmp_path / "record.jsonl"
    command = [sys.executable, str(FAKE_LSP), "error-on-initialize", str(record)]
    monkeypatch.setattr(language_server, "_bundled_command", lambda: command)
    root = write_project(tmp_path / "p", {"pkg/a.py": FOO})
    code, out, err = run_raw(root, RENAME_FOO, monkeypatch, capsys)
    expected = [message("refactor.pyright-failed"), message("refactor.checker-error", error="fake failure"),
                "  fake: initialize failed"]
    assert (code, out, err) == (1, "", CHECKS + "".join(f"{line}\n" for line in expected))
