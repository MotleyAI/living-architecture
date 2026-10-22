"""Fixes for rope's source walker (`patchedast`), the coverage it must reach, and the guard that enforces it.

rope's walker hand-lists each node's tokens and sub-nodes and finds each token by forward text search, so text a
visitor omits is skipped and a `(`, `=` or quote in it is matched as a later token. The visitors below walk the
grammar rope omits; `coverage_violations` detects any gap left, and the scope-region guard refuses it.
"""

from __future__ import annotations

import ast
import re
import sys
from typing import TypeGuard

from rope.base import ast as rope_ast
from rope.base import codeanalyze, pyscopes, simplify, utils
from rope.refactor import patchedast

_rope_joined_str = patchedast._PatchingASTWalker._JoinedStr
_rope_scope_regions = pyscopes.GlobalScope._calculate_scope_regions

_PLAIN_PREFIX = r"(?:(?<!\w)(?:[uU]|[bB][rR]?|[rR][bB]?))?"
_FORMATTED_PREFIX = r"(?<!\w)(?:[fFtT][rR]?|[rR][fFtT])"
_ANY_PREFIX = r"[bBfFrRtTuU]{,4}"

_UNREGIONED = (ast.expr_context, ast.operator, ast.boolop, ast.unaryop, ast.cmpop)
_NEWLINE = re.compile(r"\r\n|\r|\n")
_TRIVIA = re.compile(r"(?:[\s()]|\\(?:\r\n|\r|\n)|#[^\r\n]*)*")


class WalkerGap(Exception):
    """rope's walker cannot cover the module at `path`; `line` is the construct's."""

    def __init__(self, path: str, line: int) -> None:
        super().__init__(path, line)
        self.path = path
        self.line = line


def _arg(self, node):
    children = [node.arg]
    if node.annotation is not None:
        children.extend([":", node.annotation])
    self._handle(node, children)


def _arguments(self, node):
    children: list = []

    def sep() -> None:
        if children:
            children.append(",")

    posonly = list(node.posonlyargs)
    args = posonly + list(node.args)
    defaults = [None] * (len(args) - len(node.defaults)) + list(node.defaults)
    for index, (arg, default) in enumerate(zip(args, defaults)):
        sep()
        self._add_args_to_children(children, arg, default)
        if posonly and index == len(posonly) - 1:
            children.extend([",", "/"])
    if node.vararg is not None or node.kwonlyargs:
        sep()
        children.append("*")
        if node.vararg is not None:
            children.append(node.vararg)
    for arg, default in zip(node.kwonlyargs, node.kw_defaults):
        sep()
        self._add_args_to_children(children, arg, default)
    if node.kwarg is not None:
        sep()
        children.extend(["**", node.kwarg])
    self._handle(node, children)


def _handle_function_def_node(self, node, is_async):
    children = []
    for decorator in node.decorator_list:
        children.extend(("@", decorator))
    children.extend(["async", "def"] if is_async else ["def"])
    children.append(node.name)
    self._add_type_params(node, children)
    children.extend(["(", node.args, ")"])
    if node.returns is not None:
        children.extend(["->", node.returns])
    children.append(":")
    children.extend(node.body)
    self._handle(node, children)


def _ClassDef(self, node):
    children = []
    for decorator in node.decorator_list:
        children.extend(("@", decorator))
    children.extend(["class", node.name])
    self._add_type_params(node, children)
    arguments = sorted([*node.bases, *node.keywords], key=lambda n: (n.lineno, n.col_offset))
    if arguments:
        children.extend(["(", *self._child_nodes(arguments, ","), ")"])
    children.append(":")
    children.extend(node.body)
    self._handle(node, children)


def _TryFinally(self, node):
    children = ["try", ":", *node.body, *node.handlers]
    if node.orelse:
        children.extend(["else", ":", *node.orelse])
    children.extend(["finally", ":", *node.finalbody])
    self._handle(node, children)


def _JoinedStr(self, node):
    """rope's, with the region extended over every implicitly concatenated piece."""
    if sys.version_info >= (3, 12):
        _, end = self.ast_adapter[node]
    else:
        offset = self.source.offset
        _, end = self.source.consume_string(end=self._find_next_statement_start())
        self.source.offset = offset
    _rope_joined_str(self, node)
    if self.source.offset < end:
        skipped = self.source[self.source.offset : end]
        self.source.offset = end
        node.region = (node.region[0], end)
        if self.children:
            node.sorted_children[-1] += skipped


if sys.version_info >= (3, 14):
    _INTERPOLATED: tuple[type[ast.expr], ...] = (ast.JoinedStr, ast.TemplateStr)

    def _TemplateStr(self, node):
        """Walked as the equivalent f-string."""
        values: list[ast.expr] = [
            ast.copy_location(ast.FormattedValue(part.value, part.conversion, part.format_spec), part)
            if isinstance(part, ast.Interpolation)
            else part
            for part in node.values
        ]
        joined = ast.copy_location(ast.JoinedStr(values), node)
        self._JoinedStr(joined)
        node.region = joined.region
        if self.children:
            node.sorted_children = joined.sorted_children
else:
    _INTERPOLATED = (ast.JoinedStr,)


def _string_pattern() -> str:
    return codeanalyze.get_string_pattern_with_prefix(_PLAIN_PREFIX)


def _formatted_string_pattern() -> str:
    return codeanalyze.get_string_pattern_with_prefix(_FORMATTED_PREFIX)


def _any_string_pattern() -> str:
    return codeanalyze.get_string_pattern_with_prefix(_ANY_PREFIX, prefix_group_name="prefix")


@utils.cached(7)
def _real_code(source: str) -> str:
    """rope's `simplify.real_code`, keeping t-strings' text like f-strings'."""
    collector = codeanalyze.ChangeCollector(source)
    for start, end, groups in simplify.ignored_regions(source):
        if source[start] == "#":
            collector.add_change(start, end, " " * (end - start))
        elif not set(groups.get("prefix", "").lower()) & {"f", "t"}:
            collector.add_change(start, end, '"%s"' % (" " * (end - start - 2)))
    source = collector.get_changed() or source
    collector = codeanalyze.ChangeCollector(source)
    parens = 0
    for match in simplify._parens.finditer(source):
        c = match.group()
        if c in "({[":
            parens += 1
        if c in ")}]":
            parens -= 1
        if c == "\n" and parens > 0:
            collector.add_change(match.start(), match.start() + 1, " ")
    source = collector.get_changed() or source
    return source.replace("\\\n", "  ").replace("\t", " ").replace(";", "\n")


def _line_starts(source: str) -> list[int]:
    return [0, *(m.end() for m in _NEWLINE.finditer(source))]


def _char_offset(source: str, starts: list[int], line: int, col: int) -> int:
    start = starts[line - 1]
    head = source[start : start + col]
    return start + (col if head.isascii() else len(head.encode()[:col].decode()))


def char_offset(source: str, line: int, col: int) -> int:
    """The character offset of an AST position (1-based line, UTF-8 byte column)."""
    return _char_offset(source, _line_starts(source), line, col)


def coverage_violations(tree: ast.AST, source: str) -> list[tuple[int, str]]:
    """`(line, kind)` of every node rope's walk left uncovered, in source order; `[]` when covered."""
    starts = _line_starts(source)
    found: list[tuple[int, int, str]] = []

    def visit(node: ast.AST, parent_walked: bool, parent_start: tuple[int, int]) -> None:
        if isinstance(node, _UNREGIONED):
            return
        line = getattr(node, "lineno", None)
        start: tuple[int, int] = parent_start if line is None else (line, getattr(node, "col_offset", 0))
        region: tuple[int, int] | None = vars(node).get("region")
        walked = region is not None
        if isinstance(node, ast.withitem):
            walked = parent_walked
        elif not walked:
            if parent_walked:
                found.append((*start, "unwalked"))
        elif region is not None and _is_string(node) and not _covers(node, region, source, starts):
            found.append((*start, "string"))
        if not isinstance(node, _INTERPOLATED):
            for child in ast.iter_child_nodes(node):
                visit(child, walked, start)

    visit(tree, False, (1, 0))
    return [(line, kind) for line, _, kind in sorted(found)]


def _is_string(node: ast.AST) -> TypeGuard[ast.expr]:
    return isinstance(node, _INTERPOLATED) or (isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)))


def _covers(node: ast.expr, region: tuple[int, int], source: str, starts: list[int]) -> bool:
    region_start, region_end = region
    start = _char_offset(source, starts, node.lineno, node.col_offset)
    end = _char_offset(source, starts, node.end_lineno or node.lineno, node.end_col_offset or 0)
    return (
        region_start <= start
        and end <= region_end
        and _TRIVIA.fullmatch(source[region_start:start] + source[end:region_end]) is not None
    )


def _is_walker_failure(exc: BaseException) -> bool:
    """A token mismatch, or an exception raised inside rope's walker itself."""
    if isinstance(exc, patchedast.MismatchedTokenError):
        return True
    tb = exc.__traceback__
    if tb is None:
        return False
    while tb.tb_next is not None:
        tb = tb.tb_next
    return tb.tb_frame.f_code.co_filename == patchedast.__file__


def _walk(source: str) -> list[tuple[int, str]] | None:
    """The coverage violations of walking `source`; `None` when the walk is clean."""
    tree = rope_ast.parse(source)
    try:
        patchedast.patch_ast(tree, source)
    except Exception as exc:
        if not _is_walker_failure(exc):
            raise
        return coverage_violations(tree, source)
    return coverage_violations(tree, source) or None


def walk_gap_line(source: str) -> int | None:
    """The line of the first construct rope's walker cannot cover; `None` when it covers the module."""
    violations = _walk(source)
    if violations is None:
        return None
    if violations:
        return violations[0][0]
    starts = _line_starts(source)
    for stmt in rope_ast.parse(source).body:
        decorators = getattr(stmt, "decorator_list", [])
        start = starts[decorators[0].lineno - 1] if decorators else _char_offset(source, starts, stmt.lineno, stmt.col_offset)
        end = _char_offset(source, starts, stmt.end_lineno or stmt.lineno, stmt.end_col_offset or 0)
        if _walk(source[start:end]) is not None:
            return stmt.lineno
    return 1


def _gap(scope, source: str) -> WalkerGap:
    resource = scope.pyobject.get_resource()
    return WalkerGap(resource.path if resource is not None else "<string>", walk_gap_line(source) or 1)


def _check_scope_regions(self) -> None:
    """rope's scope-region walk, refusing a module it cannot cover."""
    source = self._get_source()
    try:
        _rope_scope_regions(self)
    except Exception as exc:
        if not _is_walker_failure(exc):
            raise
        raise _gap(self, source) from None
    if coverage_violations(self.pyobject.get_ast(), source):
        raise _gap(self, source)


_checked_scope_regions = utils.saveit(_check_scope_regions)


def apply_rope_patches() -> None:
    walker = patchedast._PatchingASTWalker
    walker._arg = _arg
    walker._arguments = _arguments
    walker._handle_function_def_node = _handle_function_def_node
    walker._ClassDef = _ClassDef
    walker._TryFinally = _TryFinally
    walker._JoinedStr = _JoinedStr
    if sys.version_info >= (3, 14):
        walker._TemplateStr = _TemplateStr
    codeanalyze.get_string_pattern = _string_pattern
    codeanalyze.get_formatted_string_pattern = _formatted_string_pattern
    patchedast._Source._string_pattern = None
    codeanalyze.get_any_string_pattern = _any_string_pattern
    simplify._str = re.compile(f"{codeanalyze.get_comment_pattern()}|{_any_string_pattern()}")
    simplify.real_code = _real_code
    pyscopes.GlobalScope._calculate_scope_regions = _checked_scope_regions
