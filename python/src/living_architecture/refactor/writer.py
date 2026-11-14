"""A refactor's file writes and moves, applied all or nothing: each file through a same-directory temporary file."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class WriteFailed(Exception):
    """Writing `path` failed; every file already written is restored."""

    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.path = path


class FileChanged(Exception):
    """The file at `path` changed after the refactor read it."""

    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.path = path


class FileWrite(BaseModel):
    """A file's new bytes, with the bytes the refactor read (None: a new file)."""

    model_config = ConfigDict(frozen=True)

    rel: str
    old: bytes | None
    new: bytes


class FileMove(BaseModel):
    """A file or directory moved, after the writes."""

    model_config = ConfigDict(frozen=True)

    rel: str
    dest: str


def _replace(path: Path, data: bytes) -> None:
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".la-tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        if path.exists():
            os.chmod(temp, path.stat().st_mode & 0o7777)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def _tracked(root: Path, rel: str) -> bool:
    """Git tracks `rel` (relative to `root`, inside a work tree)."""
    try:
        proc = subprocess.run(["git", "ls-files", "--error-unmatch", "--", rel], cwd=root, capture_output=True, check=False)
    except OSError:
        return False
    return proc.returncode == 0


def _move(root: Path, rel: str, dest: str) -> None:
    """`git mv` for a tracked file or directory, so the move is staged as before; else a rename."""
    if (root / ".git").exists() and _tracked(root, rel):
        proc = subprocess.run(["git", "mv", "--", rel, dest], cwd=root, capture_output=True, check=False)
        if proc.returncode != 0:
            raise OSError(proc.returncode, rel)
        return
    os.replace(root / rel, root / dest)


def _restore(root: Path, done: list[FileWrite], moved: list[FileMove]) -> None:
    for move in reversed(moved):
        _move(root, move.dest, move.rel)
    for write in reversed(done):
        if write.old is None:
            (root / write.rel).unlink(missing_ok=True)
        else:
            _replace(root / write.rel, write.old)


def verify(root: Path, writes: list[FileWrite]) -> None:
    """`FileChanged` for the first file that changed since the refactor read it."""
    for write in writes:
        path = root / write.rel
        current = path.read_bytes() if path.is_file() else None
        if current != write.old:
            raise FileChanged(write.rel)


def apply(root: Path, writes: list[FileWrite], moves: list[FileMove]) -> None:
    """Write every file, then move; on a failure restore what was done and raise `WriteFailed`."""
    verify(root, writes)
    done: list[FileWrite] = []
    moved: list[FileMove] = []
    current = ""
    try:
        for write in writes:
            current = write.rel
            _replace(root / write.rel, write.new)
            done.append(write)
        for move in moves:
            current = move.rel
            _move(root, move.rel, move.dest)
            moved.append(move)
    except OSError:
        _restore(root, done, moved)
        raise WriteFailed(current) from None
