"""The refactor writer: every file through a same-directory temporary file, moves after writes, all or nothing."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from project_files import file_tree, write_project
from refactor_cli import git
from trmv.refactor import writer
from trmv.refactor.writer import FileChanged, FileMove, FileWrite, WriteFailed, apply


def _write(rel: str, old: str | None, new: str) -> FileWrite:
    return FileWrite(rel=rel, old=None if old is None else old.encode(), new=new.encode())


def test_writes_then_moves(tmp_path: Path) -> None:
    root = write_project(tmp_path / "p", {"a.py": "a\n", "b.py": "b\n", "sub/__init__.py": ""})
    apply(root, [_write("a.py", "a\n", "A\n"), _write("new.py", None, "n\n")], [FileMove(rel="b.py", dest="sub/b.py")])
    tree = file_tree(root)
    assert {rel: tree.get(rel) for rel in ("a.py", "b.py", "new.py", "sub/b.py")} == {
        "a.py": b"A\n", "b.py": None, "new.py": b"n\n", "sub/b.py": b"b\n"}
    assert not [p for p in root.rglob("*.la-tmp")]


def test_a_replaced_file_keeps_its_mode(tmp_path: Path) -> None:
    root = write_project(tmp_path / "p", {"run.py": "a\n"})
    (root / "run.py").chmod(0o755)
    apply(root, [_write("run.py", "a\n", "b\n")], [])
    assert (root / "run.py").stat().st_mode & 0o7777 == 0o755


def test_a_file_changed_since_it_was_read_writes_nothing(tmp_path: Path) -> None:
    root = write_project(tmp_path / "p", {"a.py": "edited\n", "b.py": "b\n"})
    before = file_tree(root)
    writes = [_write("b.py", "b\n", "B\n"), _write("a.py", "a\n", "A\n")]
    with pytest.raises(FileChanged):
        apply(root, writes, [])
    assert file_tree(root) == before


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="needs a non-root user to deny a write")
def test_a_failed_move_restores_every_write(tmp_path: Path) -> None:
    root = write_project(tmp_path / "p", {"a.py": "a\n", "b.py": "b\n", "locked/__init__.py": ""})
    before = file_tree(root)
    (root / "locked").chmod(0o555)
    try:
        writes, moves = [_write("a.py", "a\n", "A\n")], [FileMove(rel="b.py", dest="locked/b.py")]
        with pytest.raises(WriteFailed) as failed:
            apply(root, writes, moves)
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


def test_every_restoration_is_attempted_and_the_unrestored_named(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = write_project(tmp_path / "p", {"a.py": "a\n", "b.py": "b\n", "c.py": "c\n"})
    real = writer._replace
    calls: dict[str, int] = {}

    def flaky(path: Path, data: bytes) -> None:
        calls[path.name] = calls.get(path.name, 0) + 1
        if (path.name, calls[path.name]) in {("c.py", 1), ("b.py", 2)}:
            raise OSError(path.name)
        real(path, data)

    monkeypatch.setattr(writer, "_replace", flaky)
    writes = [_write("a.py", "a\n", "A\n"), _write("b.py", "b\n", "B\n"), _write("c.py", "c\n", "C\n")]
    with pytest.raises(WriteFailed) as failed:
        apply(root, writes, [])
    assert (failed.value.path, failed.value.unrestored) == ("c.py", ("b.py",))
    assert file_tree(root)["a.py"] == b"a\n"


def test_a_move_that_fails_after_moving_is_rolled_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = write_project(tmp_path / "p", {"a.py": "a\n", "sub/__init__.py": ""})
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "a.py", "sub/__init__.py")
    git(root, "commit", "-q", "-m", "init")
    real = subprocess.run

    def index_write_fails(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if args[:2] == ["git", "mv"] and args[3] == "a.py":
            os.replace(root / args[3], root / args[4])
            return subprocess.CompletedProcess(args, 1)
        return real(args, **kwargs)  # pyright: ignore[reportCallIssue, reportArgumentType]

    monkeypatch.setattr(writer.subprocess, "run", index_write_fails)
    moves = [FileMove(rel="a.py", dest="sub/a.py")]
    with pytest.raises(WriteFailed) as failed:
        apply(root, [], moves)
    assert (failed.value.path, failed.value.unrestored) == ("a.py", ())
    assert {rel: file_tree(root).get(rel) for rel in ("a.py", "sub/a.py")} == {"a.py": b"a\n", "sub/a.py": None}


def test_a_tracked_move_below_the_git_root_is_staged(tmp_path: Path) -> None:
    repo = write_project(tmp_path / "repo", {"proj/a.py": "a\n", "proj/sub/__init__.py": ""})
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "proj/a.py", "proj/sub/__init__.py")
    git(repo, "commit", "-q", "-m", "init")
    apply(repo / "proj", [], [FileMove(rel="a.py", dest="sub/a.py")])
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True, check=True).stdout
    assert "R  proj/a.py -> proj/sub/a.py" in status.splitlines()


def test_a_file_is_created_where_a_move_freed_its_path(tmp_path: Path) -> None:
    root = write_project(tmp_path / "p", {"a.py": "X = 1\n"})
    apply(root, [], [FileMove(rel="a.py", dest="b.py")], [FileWrite(rel="a.py", old=None, new=b"stub\n")])
    assert ((root / "a.py").read_bytes(), (root / "b.py").read_bytes()) == (b"stub\n", b"X = 1\n")


def test_a_failed_creation_undoes_the_moves_and_writes(tmp_path: Path) -> None:
    root = write_project(tmp_path / "p", {"a.py": "X = 1\n", "use.py": "u\n", "locked/__init__.py": ""})
    before = file_tree(root)
    (root / "locked").chmod(0o555)
    try:
        writes, moves = [_write("use.py", "u\n", "U\n")], [FileMove(rel="a.py", dest="b.py")]
        creates = [FileWrite(rel="locked/stub.py", old=None, new=b"stub\n")]
        with pytest.raises(WriteFailed) as failed:
            apply(root, writes, moves, creates)
    finally:
        (root / "locked").chmod(0o755)
    assert failed.value.path == "locked/stub.py"
    assert file_tree(root) == before
