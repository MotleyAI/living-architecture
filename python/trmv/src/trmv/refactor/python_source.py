"""A Python file's text and syntax tree, with AST positions as character offsets."""

from __future__ import annotations

import ast
import bisect
import re
import unicodedata
from functools import cached_property
from pathlib import Path
from typing import TypeVar, cast

_N = TypeVar("_N", bound=ast.AST)
_NEWLINE = re.compile(r"\r\n|\r|\n")
_DEF_KEYWORD = re.compile(r"(?:async\s+)?(?:def|class)\s+")
_SEGMENT = re.compile(r"(?:\.|[^\S\r\n]|\\\r?\n|\\\r)*([^\W\d]\w*)")
_FROM = re.compile(r"from\s*\.*\s*")

Positioned = ast.expr | ast.stmt | ast.arg | ast.keyword


def _name_char(ch: str) -> bool:
    return ("_" + ch).isidentifier()


def name_end(text: str, start: int) -> int:
    """The end of the run of identifier characters (combining marks included) starting at `start`."""
    end = start
    while end < len(text) and _name_char(text[end]):
        end += 1
    return end


def every_parameter(args: ast.arguments) -> list[ast.arg]:
    """Every parameter of `args`, in declaration order."""
    return [a for a in (*args.posonlyargs, *args.args, args.vararg, *args.kwonlyargs, args.kwarg) if a is not None]


def dotted_segments(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """The spans of the dotted name's identifiers written in `text[start:end]`, in order."""
    out: list[tuple[int, int]] = []
    at = start
    while at < end:
        m = _SEGMENT.match(text, at)
        if m is None or m.start(1) >= end:
            break
        out.append(m.span(1))
        at = m.end()
        if at < end and text[at] not in ". \t\\":
            break
    return out


def nfkc(raw: str) -> str:
    """The identifier Python reads from `raw`: its NFKC normal form."""
    return unicodedata.normalize("NFKC", raw)


def same_name(raw: str, name: str) -> bool:
    """`raw` spells `name` as Python reads identifiers."""
    return nfkc(raw) == name


def line_starts(text: str) -> list[int]:
    """The offset of each line of `text`; lines end at Python's terminators `\\r\\n`, `\\r` and `\\n`."""
    return [0, *(m.end() for m in _NEWLINE.finditer(text))]


def _assigns_all(stmt: ast.stmt) -> bool:
    """`stmt` assigns, extends or appends to a module's `__all__`."""
    if isinstance(stmt, ast.Assign):
        targets = stmt.targets
    elif isinstance(stmt, (ast.AnnAssign, ast.AugAssign)):
        targets = [stmt.target]
    elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call) and isinstance(stmt.value.func, ast.Attribute):
        func = stmt.value.func
        targets = [func.value] if func.attr in ("append", "extend") else []
    else:
        return False
    return any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets)


def _exported(stmt: ast.stmt) -> list[ast.expr]:
    """What a statement on `__all__` adds: an `append` argument, else the elements of its literal."""
    value: ast.expr | None = getattr(stmt, "value", None)
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute):
        arg = value.args[0] if value.args else None
        if value.func.attr == "append":
            return [arg] if arg is not None else []
        value = arg
    return _literal_elements(value)


def _literal_elements(value: ast.expr | None) -> list[ast.expr]:
    """The elements of a list, tuple or set literal, or of such literals joined by `+`."""
    if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
        return list(value.elts)
    if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add):
        return _literal_elements(value.left) + _literal_elements(value.right)
    return []


def split_lines(text: str) -> list[str]:
    """`text`'s lines with their terminators; a final terminator opens no line."""
    starts = line_starts(text)
    return [text[s:e] for s, e in zip(starts, [*starts[1:], len(text)], strict=True) if s < e]


_CODING = re.compile(r"^[ \t\f]*#.*?coding[:=][ \t]*[-_.a-zA-Z0-9]+")


def header_lines(lines: list[str]) -> int:
    """How many leading lines are the file's header: a shebang on line 1, a coding declaration on line 1 or, below a
    blank or comment line, on line 2."""
    count = 1 if lines and lines[0].startswith("#!") else 0
    plain = bool(lines) and lines[0].strip() != "" and not lines[0].lstrip().startswith("#")
    for index, line in enumerate(lines[: 1 if plain else 2]):
        if _CODING.match(line):
            count = index + 1
    return count


def header_end(text: str) -> int:
    """The offset after the file's header."""
    lines = split_lines(text)
    return sum(len(line) for line in lines[: header_lines(lines)])


class SourceFile:
    """`text` of the file at `path` (absolute), parsed once; `tree` is None when it does not parse."""

    def __init__(self, path: Path, text: str) -> None:
        self.path = path
        self.text = text
        self._starts = line_starts(text)
        self._of_type: dict[type[ast.AST], list[ast.AST]] = {}
        try:
            self.tree: ast.Module | None = ast.parse(text)
        except (SyntaxError, ValueError):
            self.tree = None

    @cached_property
    def nodes(self) -> tuple[ast.AST, ...]:
        """Every node of `tree` in `ast.walk` order; empty when it does not parse."""
        return tuple(ast.walk(self.tree)) if self.tree is not None else ()

    def of_type(self, kind: type[_N]) -> list[_N]:
        """The nodes of `kind`, in `ast.walk` order."""
        if kind not in self._of_type:
            self._of_type[kind] = [n for n in self.nodes if isinstance(n, kind)]
        return cast("list[_N]", self._of_type[kind])

    @cached_property
    def _parents(self) -> dict[int, ast.AST]:
        return {id(c): n for n in self.nodes for c in ast.iter_child_nodes(n)}

    def parent(self, node: ast.AST) -> ast.AST | None:
        """`node`'s parent in `tree`."""
        return self._parents.get(id(node))

    @cached_property
    def _definitions(self) -> dict[tuple[int, int], ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef]:
        out: dict[tuple[int, int], ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef] = {}
        for n in self.nodes:
            if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and (span := self.name_span(n)):
                out.setdefault(span, n)
        return out

    def defined_at(self, span: tuple[int, int]) -> ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef | None:
        """The first class or function, in `ast.walk` order, whose name spans `span`."""
        return self._definitions.get(span)

    @cached_property
    def _names(self) -> dict[int, ast.Name | ast.Attribute]:
        out: dict[int, ast.Name | ast.Attribute] = {}
        for n in self.nodes:
            if isinstance(n, (ast.Name, ast.Attribute)) and (span := self.name_span(n)) is not None:
                out.setdefault(span[0], n)
        return out

    def name_at(self, start: int) -> ast.Name | ast.Attribute | None:
        """The first name or attribute, in `ast.walk` order, whose identifier starts at `start`."""
        return self._names.get(start)

    @cached_property
    def all_statements(self) -> list[ast.stmt]:
        """The module-level statements assigning, extending or appending to `__all__`."""
        return [s for s in self.tree.body if _assigns_all(s)] if self.tree is not None else []

    def all_strings(self) -> list[ast.Constant]:
        """The names the `__all__` statements export: string elements of their list, tuple or set literals, and the
        string an `append` adds."""
        return [e for s in self.all_statements for e in _exported(s) if isinstance(e, ast.Constant) and isinstance(e.value, str)]

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

    def from_path(self, node: ast.ImportFrom) -> list[tuple[int, int]]:
        """The spans of the identifiers of `from …`'s written module path."""
        written = node.module.split(".") if node.module else []
        first = self.offset(node.lineno, node.col_offset)
        head = _FROM.match(self.text, first)
        return dotted_segments(self.text, head.end() if head else first, self.span(node)[1])[: len(written)]

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
