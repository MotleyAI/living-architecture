"""A Python file's text and syntax tree, with AST positions as character offsets."""

from __future__ import annotations

import ast
import bisect
import re
import unicodedata
from pathlib import Path

_NEWLINE = re.compile(r"\r\n|\r|\n")
_DEF_KEYWORD = re.compile(r"(?:async\s+)?(?:def|class)\s+")

Positioned = ast.expr | ast.stmt | ast.arg | ast.keyword


def _name_char(ch: str) -> bool:
    return ("_" + ch).isidentifier()


def name_end(text: str, start: int) -> int:
    """The end of the run of identifier characters (combining marks included) starting at `start`."""
    end = start
    while end < len(text) and _name_char(text[end]):
        end += 1
    return end


def nfkc(raw: str) -> str:
    """The identifier Python reads from `raw`: its NFKC normal form."""
    return unicodedata.normalize("NFKC", raw)


def same_name(raw: str, name: str) -> bool:
    """`raw` spells `name` as Python reads identifiers."""
    return nfkc(raw) == name


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
            m = _DEF_KEYWORD.match(self.text, self.offset(node.lineno, node.col_offset))
            return self._name_from(m.end(), node.name) if m else None
        if isinstance(node, ast.Name):
            return self.span(node)
        if isinstance(node, ast.Attribute):
            end = self.span(node)[1]
            start = end
            while start > 0 and _name_char(self.text[start - 1]):
                start -= 1
            return (start, end) if same_name(self.text[start:end], node.attr) else None
        if isinstance(node, ast.arg):
            return self._name_from(self.offset(node.lineno, node.col_offset), node.arg)
        if isinstance(node, ast.keyword) and node.arg is not None:
            return self._name_from(self.offset(node.lineno, node.col_offset), node.arg)
        return self._bound_name_span(node)

    def _name_from(self, start: int, name: str) -> tuple[int, int] | None:
        """The identifier starting at `start`, if it spells `name`."""
        end = name_end(self.text, start)
        return (start, end) if end > start and same_name(self.text[start:end], name) else None

    def _bound_name_span(self, node: ast.AST) -> tuple[int, int] | None:
        """The span of the name an import alias, an `except ... as` or a `match` capture binds."""
        if isinstance(node, ast.alias):
            return self._word(node, node.asname or node.name.split(".")[0], last=node.asname is not None)
        if isinstance(node, ast.ExceptHandler) and node.name and node.type is not None:
            after = self.span(node.type)[1]
            m = re.compile(r"(?:\s|\)|#[^\r\n]*+|\\\r?\n)*+as\s+").match(self.text, after)
            return self._name_from(m.end(), node.name) if m else None
        if isinstance(node, ast.MatchAs | ast.MatchStar) and node.name:
            return self._word(node, node.name, last=True)
        if isinstance(node, ast.MatchMapping) and node.rest:
            return self._word(node, node.rest, last=True)
        return None

    def _word(self, node: ast.alias | ast.pattern, word: str, *, last: bool) -> tuple[int, int] | None:
        start = self.offset(node.lineno, node.col_offset)
        end = self.offset(node.end_lineno or node.lineno, node.end_col_offset or 0)
        return self.word(start, end, word, last=last)

    def word(self, start: int, end: int, word: str, *, last: bool = False) -> tuple[int, int] | None:
        """The first or last whole identifier between `start` and `end` that spells `word`."""
        found: list[tuple[int, int]] = []
        at = start
        while at < end:
            stop = min(name_end(self.text, at), end)
            if stop > at and same_name(self.text[at:stop], word):
                found.append((at, stop))
            at = max(stop, at + 1)
        if not found:
            return None
        return found[-1] if last else found[0]
