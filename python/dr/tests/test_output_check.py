"""Every Python refactor checks the files it would write: each still parses, and its bytes decode to its text."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from deterministic_refactor.config import current_format
from deterministic_refactor.contract import message
from deterministic_refactor.refactor import rename_map, rope_refactor
from deterministic_refactor.refactor.locators import RefactorError
from deterministic_refactor.refactor.move_project import MoveProject
from deterministic_refactor.refactor.moved_symbol import MovedSymbol
from deterministic_refactor.refactor.output_check import checked_create, checked_write
from deterministic_refactor.refactor.python_project import Snapshot
from deterministic_refactor.refactor.text_edits import TextEdit
from deterministic_refactor.refactor.writer import FileWrite
from project_files import file_tree, write_project
from refactor_cli import run

BROKEN = "def f(:\n"
FLAGS = pytest.mark.parametrize("flags", [[], ["--apply"]], ids=["dry-run", "apply"])


def _refused(root: Path, argv: list[str], path: str, monkeypatch: pytest.MonkeyPatch,
             capsys: pytest.CaptureFixture[str]) -> None:
    """`argv` exits 1 with only the unparsable finding naming `path`, and changes no file."""
    before = file_tree(root)
    assert run(root, argv, monkeypatch, capsys) == (1, "", message("refactor.unparsable", path=path) + "\n")
    assert file_tree(root) == before


@FLAGS
def test_a_move_whose_text_does_not_parse_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], flags: list[str]
) -> None:
    real: Callable[[MoveProject, str, MovedSymbol, str], dict[str, str]] = rope_refactor.symbol_move_texts

    def broken(project: MoveProject, source: str, moved: MovedSymbol, dest: str) -> dict[str, str]:
        texts = real(project, source, moved, dest)
        return {**texts, dest: texts[dest] + BROKEN}

    monkeypatch.setattr(rope_refactor, "symbol_move_texts", broken)
    root = write_project(tmp_path / "proj", {"pkg/a.py": "def f():\n    return 1\n", "pkg/b.py": '"""B."""\n'})
    argv = [*flags, "move-symbol", "--file", "pkg/a.py", "--symbol", "f", "--dest", "pkg/b.py"]
    _refused(root, argv, "pkg/b.py", monkeypatch, capsys)


ENGINE = ("class Engine:\n    def save_model(self, m: int) -> int:\n        return m\n\n"
          "    def save(self, m: int) -> int:\n        return self.save_model(m)\n")
VALUE = {"pkg/a.py": "value = 1\nprint(value)\n"}
RENAMES = {
    "rename": (VALUE, ["rename", "--file", "pkg/a.py", "--symbol", "value", "--new-name", "valu"], "pkg/a.py"),
    "rename-map": ({**VALUE, "map.yaml": "- {file: pkg/a.py, symbol: value, new_name: valu}\n"},
                   ["rename-map", "map.yaml"], "pkg/a.py"),
    "retarget": ({"pkg/engine.py": ENGINE, "pkg/use.py": "from pkg.engine import Engine\n\n\ndef use(engine: Engine) -> None:\n    engine.save(1)\n"},
                 ["retarget", "--file", "pkg/engine.py", "--symbol", "Engine.save", "--target", "Engine.save_model"],
                 "pkg/use.py"),
}


@FLAGS
@pytest.mark.parametrize(("files", "argv", "path"), list(RENAMES.values()), ids=list(RENAMES))
def test_a_rename_whose_text_does_not_parse_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], flags: list[str],
    files: dict[str, str], argv: list[str], path: str,
) -> None:
    real: Callable[[str, list[TextEdit]], str] = rename_map.apply_edits
    monkeypatch.setattr(rename_map, "apply_edits", lambda text, edits: real(text, edits) + BROKEN)
    root = write_project(tmp_path / "proj", files)
    _refused(root, [*flags, *argv], path, monkeypatch, capsys)


@FLAGS
def test_a_stub_that_does_not_parse_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], flags: list[str]
) -> None:
    config = (f"format: {current_format()}\nrefactor:\n  python:\n    moved_module_stub: |\n"
              "      import {new} as {removal}\n")
    root = write_project(tmp_path / "proj", {"pkg/a.py": "A = 1\n", "living-architecture.yaml": config})
    argv = [*flags, "rename", "--file", "pkg/a.py", "--new-name", "b", "--stub", "2.0"]
    _refused(root, argv, "pkg/a.py", monkeypatch, capsys)


# ---- checked_write, checked_create

BOM = b"\xef\xbb\xbf"


def _snapshot(tmp_path: Path, rel: str, data: bytes) -> Snapshot:
    (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / rel).write_bytes(data)
    return Snapshot(tmp_path)


@pytest.mark.parametrize(
    ("data", "text", "new"),
    [
        (b"x = 1\n", "y = 1\n", b"y = 1\n"),
        (BOM + b"x = 1\n", 'y = "\u00e9"\n', BOM + b'y = "\xc3\xa9"\n'),
        (b'# coding: latin-1\nx = "\xe9"\n', '# coding: latin-1\ny = "\u00e9"\n', b'# coding: latin-1\ny = "\xe9"\n'),
    ],
    ids=["utf-8", "byte-order-mark", "latin-1"],
)
def test_a_valid_text_becomes_the_files_write(tmp_path: Path, data: bytes, text: str, new: bytes) -> None:
    snapshot = _snapshot(tmp_path, "pkg/a.py", data)
    assert checked_write(snapshot, "pkg/a.py", text) == FileWrite(rel="pkg/a.py", old=data, new=new)


def test_a_text_the_encoding_cannot_hold_is_refused(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path, "pkg/a.py", b"# coding: ascii\nx = 1\n")
    with pytest.raises(RefactorError) as refused:
        checked_write(snapshot, "pkg/a.py", '# coding: ascii\nx = "\u00e9"\n')
    assert str(refused.value) == message("refactor.unencodable", path="pkg/a.py", encoding="ascii")


@pytest.mark.parametrize(
    ("text", "declared"),
    [('# coding: utf-8\nx = "\u00e9"\n', "utf-8"), ('# coding: cp437\nx = "\u00e9"\n', "cp437"),
     ('# coding: no-such-codec\nx = "\u00e9"\n', "no-such-codec"), ('x = "\u00e9"\n', "utf-8")],
    ids=["undecodable", "another-text", "unknown-codec", "declaration-removed"],
)
def test_bytes_that_decode_to_another_text_are_refused(tmp_path: Path, text: str, declared: str) -> None:
    snapshot = _snapshot(tmp_path, "pkg/a.py", b'# coding: latin-1\nx = "\xe9"\n')
    with pytest.raises(RefactorError) as refused:
        checked_write(snapshot, "pkg/a.py", text)
    assert str(refused.value) == message("refactor.unencodable", path="pkg/a.py", encoding=declared)


def test_a_text_that_does_not_parse_is_refused(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path, "pkg/a.py", b"x = 1\n")
    with pytest.raises(RefactorError) as refused:
        checked_write(snapshot, "pkg/a.py", BROKEN)
    assert str(refused.value) == message("refactor.unparsable", path="pkg/a.py")


@pytest.mark.parametrize(("rel", "data"), [("pkg/a.py", b"def g(:\n"), ("notes.md", b"# Notes\n")],
                         ids=["unparsed-before", "not-python"])
def test_only_a_python_file_that_parsed_is_parse_checked(tmp_path: Path, rel: str, data: bytes) -> None:
    snapshot = _snapshot(tmp_path, rel, data)
    assert checked_write(snapshot, rel, BROKEN) == FileWrite(rel=rel, old=data, new=BROKEN.encode())


@pytest.mark.parametrize(("rel", "text"), [("pkg/new.py", 'x = "\u00e9"\n'), ("notes.md", BROKEN)],
                         ids=["python", "not-python"])
def test_a_created_file_is_written_as_utf8(rel: str, text: str) -> None:
    assert checked_create(rel, text) == FileWrite(rel=rel, old=None, new=text.encode())


def test_a_created_python_file_that_does_not_parse_is_refused() -> None:
    with pytest.raises(RefactorError) as refused:
        checked_create("pkg/new.py", BROKEN)
    assert str(refused.value) == message("refactor.unparsable", path="pkg/new.py")
