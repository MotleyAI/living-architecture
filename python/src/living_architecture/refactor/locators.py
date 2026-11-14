"""Where a Python refactor's symbol is: an offset, a 1-based line and column, or a `--symbol` path."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
from rope.base import libutils
from rope.base.project import Project
from rope.base.resources import Resource

from living_architecture.contract import message
from living_architecture.refactor.python_source import SourceFile, split_lines
from living_architecture.refactor.symbol_path import Located, locate


class RefactorError(Exception):
    """The refactor cannot be computed; the message is user-facing."""


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
    return sum(len(lines[i]) for i in range(line - 1)) + (col - 1)


def resolve(locator: Locator, file: str) -> tuple[int, Located | None]:
    """The offset in rope's newline-normalized text of `file`, with what a `--symbol` path names."""
    text = Path(file).read_text()
    if locator.offset is not None:
        return locator.offset, None
    if locator.line is not None:
        return offset_from_line_col(text, locator.line, locator.col or 1), None
    if locator.symbol is not None:
        located = locate(SourceFile(Path(file).resolve(), text), locator.symbol, file)
        return located.offset, located
    raise RefactorError(message("refactor.no-locator"))


def resource(project: Project, path: str) -> Resource:
    resolved = Path(path).resolve()
    found = None
    if resolved.is_relative_to(Path(project.address).resolve()):
        found = libutils.path_to_resource(project, str(resolved))
    if found is None:
        raise RefactorError(message("refactor.outside-project", path=path))
    return found
