"""Where a Python refactor's symbol is: an offset, a 1-based line and column, or a `--symbol` path."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from trmv.contract import message
from trmv.refactor.python_project import Snapshot
from trmv.refactor.python_source import SourceFile, split_lines
from trmv.refactor.symbol_path import Located, locate


class RefactorError(Exception):
    """The refactor cannot be computed; the message is user-facing."""


def named_source(snapshot: Snapshot, rel: str) -> SourceFile:
    """The source of `rel`, a file the command names; `refactor.file-undecodable` when it does not decode."""
    encoding = snapshot.undecodable(rel)
    if encoding is not None:
        raise RefactorError(message("refactor.file-undecodable", path=rel, encoding=encoding))
    return snapshot.source(rel)


def cannot_rename() -> RefactorError:
    return RefactorError(message("refactor.cannot-rename"))


class Locator(BaseModel):
    """Where the symbol is: an offset, a 1-based line/column, or a declaration's path in the file."""

    offset: int | None = None
    line: int | None = None
    col: int | None = None
    symbol: str | None = None


def offset_from_line_col(text: str, line: int, col: int) -> int:
    lines = split_lines(text)
    if not 1 <= line <= len(lines):
        raise RefactorError(message("refactor.line-out-of-range", line=line, count=len(lines)))
    width = len(lines[line - 1].rstrip("\r\n"))
    if not 1 <= col <= width + 1:
        raise RefactorError(message("refactor.col-out-of-range", col=col, line=line, count=width))
    return sum(len(lines[i]) for i in range(line - 1)) + (col - 1)


def resolve(locator: Locator, source: SourceFile, shown: str) -> tuple[int, Located | None]:
    """The offset in the text of `source` (the file named `shown`), with what a `--symbol` path names."""
    text = source.text
    if locator.offset is not None:
        if not 0 <= locator.offset <= len(text):
            raise RefactorError(message("refactor.offset-out-of-range", offset=locator.offset, count=len(text)))
        return locator.offset, None
    if locator.line is not None:
        return offset_from_line_col(text, locator.line, locator.col or 1), None
    if locator.symbol is not None:
        located = locate(source, locator.symbol, shown)
        return located.offset, located
    raise RefactorError(message("refactor.no-locator"))


def project_rel(root: Path, path: str) -> str:
    """`path` relative to the project at `root`; `refactor.outside-project` when it is not inside."""
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(root):
        raise RefactorError(message("refactor.outside-project", path=path))
    return resolved.relative_to(root).as_posix()
