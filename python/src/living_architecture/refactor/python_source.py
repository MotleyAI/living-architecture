"""A Python file's text and syntax tree, with AST positions as character offsets."""

from __future__ import annotations

import ast
import bisect
import re
from pathlib import Path

_NEWLINE = re.compile(r"\r\n|\r|\n")
_DEF_NAME = re.compile(r"(?:async\s+)?(?:def|class)\s+(\w+)")

Positioned = ast.expr | ast.stmt | ast.arg | ast.keyword


def line_starts(text: str) -> list[int]:
    """The offset of each line of `text`; lines end at Python's terminators `\\r\\n`, `\\r` and `\\n`."""
    return [0, *(m.end() for m in _NEWLINE.finditer(text))]


def split_lines(text: str) -> list[str]:
    """`text`'s lines with their terminators; a final terminator opens no line."""
    starts = line_starts(text)
    return [text[s:e] for s, e in zip(starts, [*starts[1:], len(text)], strict=True) if s < e]


class SourceFile:
    """`text` of the file at `path` (absolute), parsed once; `tree` is None when it does not parse."""

    def __init__(self, path: Path, text: str) -> None:
        self.path = path
        self.text = text
        self._starts = line_starts(text)
        try:
            self.tree: ast.Module | None = ast.parse(text)
        except (SyntaxError, ValueError):
            self.tree = None

    def offset(self, line: int, col: int) -> int:
        """The character offset of an AST position (1-based line, UTF-8 byte column)."""
        start = self._starts[line - 1]
        head = self.text[start : start + col]
        return start + (col if head.isascii() else len(head.encode()[:col].decode(errors="ignore")))

    def line_start(self, line: int) -> int:
        """The offset of a 1-based line's first character."""
        return self._starts[line - 1]

    def line(self, offset: int) -> int:
        """The 1-based line of a character offset."""
        return bisect.bisect_right(self._starts, offset)

    def span(self, node: Positioned) -> tuple[int, int]:
        start = self.offset(node.lineno, node.col_offset)
        return start, self.offset(node.end_lineno or node.lineno, node.end_col_offset or 0)

    def segment(self, node: Positioned) -> str:
        start, end = self.span(node)
        return self.text[start:end]

    def name_span(self, node: ast.AST) -> tuple[int, int] | None:
        """The span of the identifier a node names or declares, or None."""
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            m = _DEF_NAME.match(self.text, self.offset(node.lineno, node.col_offset))
            return (m.start(1), m.end(1)) if m and m.group(1) == node.name else None
        if isinstance(node, ast.Name):
            return self.span(node)
        if isinstance(node, ast.Attribute):
            end = self.span(node)[1]
            return end - len(node.attr), end
        if isinstance(node, ast.arg):
            start = self.offset(node.lineno, node.col_offset)
            return start, start + len(node.arg)
        if isinstance(node, ast.keyword) and node.arg is not None:
            start = self.offset(node.lineno, node.col_offset)
            return start, start + len(node.arg)
        return self._bound_name_span(node)

    def _bound_name_span(self, node: ast.AST) -> tuple[int, int] | None:
        """The span of the name an import alias, an `except ... as` or a `match` capture binds."""
        if isinstance(node, ast.alias):
            return self._word(node, node.asname or node.name.split(".")[0], last=node.asname is not None)
        if isinstance(node, ast.ExceptHandler) and node.name:
            m = re.compile(rf"\bas\s+({re.escape(node.name)})\b").search(self.text, self.offset(node.lineno, node.col_offset))
            return (m.start(1), m.end(1)) if m else None
        if isinstance(node, ast.MatchAs | ast.MatchStar) and node.name:
            return self._word(node, node.name, last=True)
        if isinstance(node, ast.MatchMapping) and node.rest:
            return self._word(node, node.rest, last=True)
        return None

    def _word(self, node: ast.alias | ast.pattern, word: str, *, last: bool) -> tuple[int, int] | None:
        """The first or last whole-word `word` within `node`'s span."""
        start = self.offset(node.lineno, node.col_offset)
        end = self.offset(node.end_lineno or node.lineno, node.end_col_offset or 0)
        found = [m.span() for m in re.finditer(rf"(?<!\w){re.escape(word)}(?!\w)", self.text[start:end])]
        if not found:
            return None
        s, e = found[-1] if last else found[0]
        return start + s, start + e
