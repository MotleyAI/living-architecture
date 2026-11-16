"""la renders a refactor's changes exactly as rope's change descriptions did."""

from __future__ import annotations

from pathlib import Path

import pytest
from rope.base.change import ChangeContents, ChangeSet, MoveResource
from rope.base.project import Project

from living_architecture.refactor.diff_render import edit_description, move_description

# Each vector: the file's text as read, and as written.
EDITS: dict[str, tuple[str, str]] = {
    "lf": ("def foo() -> int:\n    return 1\n", "def bar() -> int:\n    return 1\n"),
    "no-final-newline": ("x = 1\nfoo()", "x = 1\nbar()"),
    "final-newline-added": ("foo()", "bar()\n"),
    "empty-file": ("", "bar = 1\n"),
    "emptied": ("foo = 1\n", ""),
    "crlf": ("x = 1\r\nfoo()\r\n", "x = 1\r\nbar()\r\n"),
    "lone-cr": ("x = 1\rfoo()\r", "x = 1\rbar()\r"),
    "mixed": ("x = 1\r\nfoo()\ny = 2\r", "x = 1\r\nbar()\ny = 2\r"),
    "non-ascii": ('s = "é😀"\nfoo()\n', 's = "é😀"\nbar()\n'),
    "many-hunks": ("".join(f"line{i} = foo\n" if i in (2, 40) else f"line{i} = {i}\n" for i in range(60)),
                   "".join(f"line{i} = bar\n" if i in (2, 40) else f"line{i} = {i}\n" for i in range(60))),
}
PATHS = ["pkg/a.py", "pkg/é😀/módulo.py", "a b/c.py"]


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


@pytest.fixture
def project(tmp_path: Path) -> Project:
    for rel in [*PATHS, "pkg/moved.py"]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("", encoding="utf-8")
    # rope documents `ropefolder=None` (no rope folder); its signature infers `str` from the default.
    return Project(str(tmp_path), ropefolder=None)  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("rel", PATHS)
@pytest.mark.parametrize("vector", sorted(EDITS))
def test_an_edit_renders_as_ropes_description(project: Project, vector: str, rel: str) -> None:
    old, new = EDITS[vector]
    change = ChangeContents(project.get_resource(rel), _normalize(new), old_contents=_normalize(old))
    assert edit_description(rel, old, new) == change.get_description()


@pytest.mark.parametrize("rel", PATHS)
def test_a_move_renders_as_ropes_description(project: Project, rel: str) -> None:
    dest = str(Path(rel).with_name("moved.py").as_posix())
    assert move_description(rel, dest) == MoveResource(project.get_resource(rel), dest).get_description()


def test_an_edit_and_a_move_render_as_ropes_change_set(project: Project) -> None:
    old, new = EDITS["crlf"]
    changes = ChangeSet("")
    changes.add_change(ChangeContents(project.get_resource("pkg/a.py"), _normalize(new), old_contents=_normalize(old)))
    changes.add_change(MoveResource(project.get_resource("pkg/é😀/módulo.py"), "pkg/é😀/nuevo.py"))
    expected = sorted((c.resource.path, c.get_description()) for c in changes.changes)
    actual = sorted([("pkg/a.py", edit_description("pkg/a.py", old, new)),
                     ("pkg/é😀/módulo.py", move_description("pkg/é😀/módulo.py", "pkg/é😀/nuevo.py"))])
    assert "".join(text + "\n" for _, text in actual) == "".join(text + "\n" for _, text in expected)
