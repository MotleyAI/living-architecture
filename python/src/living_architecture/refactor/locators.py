"""Where a Python refactor's symbol is: an offset, a 1-based line and column, or a `--symbol` path."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel
from rope.base import libutils
from rope.base.fscommands import read_str_coding
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
    width = len(lines[line - 1].rstrip("\r\n"))
    if not 1 <= col <= width + 1:
        raise RefactorError(message("refactor.col-out-of-range", col=col, line=line, count=width))
    return sum(len(lines[i]) for i in range(line - 1)) + (col - 1)


def _text(file: str) -> str:
    """`file` decoded by its coding cookie (else UTF-8), newlines normalized as rope reads it."""
    data = Path(file).read_bytes()
    return data.decode(read_str_coding(data) or "utf-8").replace("\r\n", "\n").replace("\r", "\n")


def resolve(locator: Locator, file: str) -> tuple[int, Located | None]:
    """The offset in rope's newline-normalized text of `file`, with what a `--symbol` path names."""
    text = _text(file)
    if locator.offset is not None:
        if not 0 <= locator.offset <= len(text):
            raise RefactorError(message("refactor.offset-out-of-range", offset=locator.offset, count=len(text)))
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
