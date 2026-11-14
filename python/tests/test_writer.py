"""The refactor writer: every file through a same-directory temporary file, moves after writes, all or nothing."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from project_files import file_tree, write_project
from refactor_cli import git

from living_architecture.refactor.writer import FileChanged, FileMove, FileWrite, WriteFailed, apply


def _write(rel: str, old: str | None, new: str) -> FileWrite:
    return FileWrite(rel=rel, old=None if old is None else old.encode(), new=new.encode())


def test_writes_then_moves(tmp_path: Path) -> None:
    root = write_project(tmp_path / "p", {"a.py": "a\n", "b.py": "b\n", "sub/__init__.py": ""})
    apply(root, [_write("a.py", "a\n", "A\n"), _write("new.py", None, "n\n")], [FileMove(rel="b.py", dest="sub/b.py")])
    tree = file_tree(root)
    assert {rel: tree.get(rel) for rel in ("a.py", "b.py", "new.py", "sub/b.py")} == {
        "a.py": b"A\n", "b.py": None, "new.py": b"n\n", "sub/b.py": b"b\n"}
    assert not [p for p in root.rglob("*.la-tmp")]


def test_a_file_changed_since_it_was_read_writes_nothing(tmp_path: Path) -> None:
    root = write_project(tmp_path / "p", {"a.py": "edited\n", "b.py": "b\n"})
    before = file_tree(root)
    with pytest.raises(FileChanged):
        apply(root, [_write("b.py", "b\n", "B\n"), _write("a.py", "a\n", "A\n")], [])
    assert file_tree(root) == before


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="needs a non-root user to deny a write")
def test_a_failed_move_restores_every_write(tmp_path: Path) -> None:
    root = write_project(tmp_path / "p", {"a.py": "a\n", "b.py": "b\n", "locked/__init__.py": ""})
    before = file_tree(root)
    (root / "locked").chmod(0o555)
    try:
        with pytest.raises(WriteFailed) as failed:
            apply(root, [_write("a.py", "a\n", "A\n")], [FileMove(rel="b.py", dest="locked/b.py")])
    finally:
        (root / "locked").chmod(0o755)
    assert failed.value.path == "b.py"
    assert file_tree(root) == before


def test_a_tracked_file_moves_with_git_and_an_untracked_one_without(tmp_path: Path) -> None:
    root = write_project(tmp_path / "p", {"tracked.py": "t\n", "sub/__init__.py": ""})
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "tracked.py", "sub/__init__.py")
    git(root, "commit", "-q", "-m", "init")
    (root / "loose.py").write_text("l\n", encoding="utf-8")
    apply(root, [], [FileMove(rel="tracked.py", dest="sub/tracked.py"), FileMove(rel="loose.py", dest="sub/loose.py")])
    status = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=True).stdout
    assert "R  tracked.py -> sub/tracked.py" in status.splitlines()
    assert "?? sub/loose.py" in status.splitlines()
    assert (root / "sub/loose.py").read_text(encoding="utf-8") == "l\n"
