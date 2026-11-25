"""A refactor's file writes and moves, applied all or nothing: each file through a same-directory temporary file."""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class WriteFailed(Exception):
    """Writing `path` failed; every file already written is restored but the `unrestored` paths."""

    def __init__(self, path: str, unrestored: tuple[str, ...] = ()) -> None:
        super().__init__(path)
        self.path = path
        self.unrestored = unrestored


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
    """`git mv` for a tracked file or directory, so the move is staged; else a rename."""
    if _tracked(root, rel):
        proc = subprocess.run(["git", "mv", "--", rel, dest], cwd=root, capture_output=True, check=False)
        if proc.returncode != 0:
            raise OSError(proc.returncode, rel)
        return
    os.replace(root / rel, root / dest)


def _restore(root: Path, done: list[FileWrite], moved: list[FileMove]) -> list[str]:
    """Undo every move and write, each attempted whatever failed before it; the paths left changed."""
    left: list[str] = []
    for move in reversed(moved):
        try:
            _move(root, move.dest, move.rel)
        except OSError:
            left.append(move.rel)
    for write in reversed(done):
        try:
            if write.old is None:
                (root / write.rel).unlink(missing_ok=True)
            else:
                _replace(root / write.rel, write.old)
        except OSError:
            left.append(write.rel)
    return sorted(left)


def _moved(root: Path, move: FileMove) -> bool:
    """A failed move that still took effect: the source gone, the destination there."""
    return not os.path.lexists(root / move.rel) and os.path.lexists(root / move.dest)


def verify(root: Path, writes: list[FileWrite]) -> None:
    """`FileChanged` for the first file that changed since the refactor read it."""
    for write in writes:
        path = root / write.rel
        current = path.read_bytes() if path.is_file() else None
        if current != write.old:
            raise FileChanged(write.rel)


def apply(root: Path, writes: list[FileWrite], moves: list[FileMove], creates: Sequence[FileWrite] = (),
          unchanged: Sequence[FileWrite] = ()) -> None:
    """Write every file, then move, then create the files the moves free; on a failure restore what was done and raise
    `WriteFailed`; `FileChanged` first when a write or an `unchanged` read changed since it was read."""
    verify(root, [*writes, *unchanged])
    done: list[FileWrite] = []
    moved: list[FileMove] = []
    created: list[FileWrite] = []
    current = ""
    try:
        for write in writes:
            current = write.rel
            _replace(root / write.rel, write.new)
            done.append(write)
        for move in moves:
            current = move.rel
            try:
                _move(root, move.rel, move.dest)
            except OSError:
                if _moved(root, move):
                    moved.append(move)
                raise
            moved.append(move)
        for create in creates:
            current = create.rel
            _replace(root / create.rel, create.new)
            created.append(create)
    except OSError:
        left = [c.rel for c in created if not _unlinked(root / c.rel)]
        raise WriteFailed(current, tuple(sorted([*left, *_restore(root, done, moved)]))) from None


def _unlinked(path: Path) -> bool:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return False
    return True
