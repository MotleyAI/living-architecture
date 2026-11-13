"""Fixes for rope's source walker (`patchedast`), the coverage it must reach, and the guard that enforces it.

rope's walker hand-lists each node's tokens and sub-nodes and finds each token by forward text search, so text a
visitor omits is skipped and a `(`, `=` or quote in it is matched as a later token. The visitors below walk the
grammar rope omits; `coverage_violations` detects any gap left, and the scope-region guard refuses it.

rope's function model lists only positional-or-keyword parameters plus `*args`/`**kwargs`; the patches below add
positional-only parameters to its positional binding vector and keyword-only ones to its scope and keyword lookup.
"""

from __future__ import annotations

import ast
import re
import sys
from typing import TypeGuard

from rope.base import ast as rope_ast
from rope.base import (
    builtins,
    codeanalyze,
    evaluate,
    pynames,
    pynamesdef,
    pyobjects,
    pyobjectsdef,
    pyscopes,
    simplify,
    utils,
    worder,
)
from rope.base.oi.type_hinting.factory import get_type_hinting_factory
from rope.base.pyobjects import PyObject
from rope.refactor import patchedast
from typing_extensions import override

_rope_joined_str = patchedast._PatchingASTWalker._JoinedStr
_rope_scope_regions = pyscopes.GlobalScope._calculate_scope_regions
_rope_primary_and_pyname_at = evaluate.ScopeNameFinder.get_primary_and_pyname_at

_PLAIN_PREFIX = r"(?:(?<!\w)(?:[uU]|[bB][rR]?|[rR][bB]?))?"
_FORMATTED_PREFIX = r"(?<!\w)(?:[fFtT][rR]?|[rR][fFtT])"
_ANY_PREFIX = r"(?:(?<!\w)[bBfFrRtTuU]{1,4})?"

_UNREGIONED = (ast.expr_context, ast.operator, ast.boolop, ast.unaryop, ast.cmpop)
_NEWLINE = re.compile(r"\r\n|\r|\n")
_COMMENT = re.compile(r"#[^\r\n]*")
_TRIVIA = re.compile(r"(?:[\s()]|\\[\r\n])*")


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


def _class_def(self, node):
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


def _try_finally(self, node):
    children = ["try", ":", *node.body, *node.handlers]
    if node.orelse:
        children.extend(["else", ":", *node.orelse])
    children.extend(["finally", ":", *node.finalbody])
    self._handle(node, children)


def _joined_str(self, node):
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

    def _template_str(self, node):
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
        if isinstance(node, ast.withitem):
            walked = parent_walked
        else:
            walked = region is not None
            kind = _violation(node, region, parent_walked, source, starts)
            if kind is not None:
                found.append((*start, kind))
        if not isinstance(node, _INTERPOLATED):
            for child in ast.iter_child_nodes(node):
                visit(child, walked, start)

    visit(tree, False, (1, 0))
    return [(line, kind) for line, _, kind in sorted(found)]


def _violation(
    node: ast.AST, region: tuple[int, int] | None, parent_walked: bool, source: str, starts: list[int]
) -> str | None:
    if region is None:
        return "unwalked" if parent_walked else None
    if _is_string(node) and not _covers(node, region, source, starts):
        return "string"
    return None


def _is_string(node: ast.AST) -> TypeGuard[ast.expr]:
    return isinstance(node, _INTERPOLATED) or (isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)))


def _covers(node: ast.expr, region: tuple[int, int], source: str, starts: list[int]) -> bool:
    region_start, region_end = region
    start = _char_offset(source, starts, node.lineno, node.col_offset)
    end = _char_offset(source, starts, node.end_lineno or node.lineno, node.end_col_offset or 0)
    return (
        region_start <= start
        and end <= region_end
        and _TRIVIA.fullmatch(_COMMENT.sub("", source[region_start:start] + source[end:region_end])) is not None
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


def _is_a_class_or_function_name_in_header(self, offset: int) -> bool:
    """rope's, also accepting an `async def` header; remove once a rope release includes python-rope/rope#859."""
    word_start = self._find_word_start(offset - 1)
    line_start = self._get_line_start(word_start)
    return " ".join(self.code[line_start:word_start].split()) in ("def", "class", "async def")


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


def _positional(fn: pyobjectsdef.PyFunction) -> list[ast.arg]:
    return [*fn.arguments.posonlyargs, *fn.arguments.args]


def _get_param_names(self: pyobjectsdef.PyFunction, special_args: bool = True) -> list[str]:
    """The positional binding vector: positional-only, positional-or-keyword, then `*args` and `**kwargs`."""
    result = [arg.arg for arg in _positional(self)]
    if special_args:
        result += [arg.arg for arg in (self.arguments.vararg, self.arguments.kwarg) if arg is not None]
    return result


def _handle_special_args(self: pyobjectsdef.PyFunction, pyobjects: list[PyObject]) -> None:
    if len(pyobjects) == len(_positional(self)):
        if self.arguments.vararg:
            pyobjects.append(builtins.get_list())
        if self.arguments.kwarg:
            pyobjects.append(builtins.get_dict())


class _KeywordOnlyName(pynamesdef.ParameterName):
    """A keyword-only parameter: never bound positionally, typed only by rope's parameter type-hint provider."""

    def __init__(self, pyfunction: pyobjectsdef.PyFunction, name: str) -> None:
        super().__init__(pyfunction, -1)
        self.name = name

    @override
    def get_object(self) -> PyObject | None:
        hint = get_type_hinting_factory(self.pyfunction.pycore.project).make_param_provider()(self.pyfunction, self.name)
        return pyobjects.get_unknown() if hint is None else pyobjects.PyObject(hint)

    @override
    def get_objects(self) -> list[PyObject | None]:
        return [self.get_object()]


def _get_parameters(self: pyobjectsdef.PyFunction) -> dict[str, pynamesdef.ParameterName]:
    """Every parameter of the function's scope, keyword-only ones included."""
    if self.parameter_pynames is None:
        result: dict[str, pynamesdef.ParameterName] = {
            name: pynamesdef.ParameterName(self, index) for index, name in enumerate(self.get_param_names())
        }
        result.update((arg.arg, _KeywordOnlyName(self, arg.arg)) for arg in self.arguments.kwonlyargs)
        self.parameter_pynames = result
    return self.parameter_pynames


def _primary_and_pyname_at(self, offset: int):
    """rope's, resolving a call's `name=` keyword only to a positional-or-keyword or keyword-only parameter, never to
    a variable of the enclosing scope."""
    if not self.worder.is_function_keyword_parameter(offset):
        return _rope_primary_and_pyname_at(self, offset)
    function = self.get_enclosing_function(offset)
    if isinstance(function, pyobjectsdef.PyFunction):
        name = self.worder.get_word_at(offset)
        bindable = {arg.arg for arg in (*function.arguments.args, *function.arguments.kwonlyargs)}
        return None, function.get_parameters().get(name) if name in bindable else None
    if isinstance(function, pyobjects.AbstractFunction):
        return None, pynames.ParameterName()
    return None, None


def apply_rope_patches() -> None:
    walker = patchedast._PatchingASTWalker
    walker._arg = _arg
    walker._arguments = _arguments
    walker._handle_function_def_node = _handle_function_def_node
    walker._ClassDef = _class_def
    walker._TryFinally = _try_finally
    walker._JoinedStr = _joined_str
    if sys.version_info >= (3, 14):
        walker._TemplateStr = _template_str
    codeanalyze.get_string_pattern = _string_pattern
    codeanalyze.get_formatted_string_pattern = _formatted_string_pattern
    patchedast._Source._string_pattern = None
    codeanalyze.get_any_string_pattern = _any_string_pattern
    simplify._str = re.compile(f"{codeanalyze.get_comment_pattern()}|{_any_string_pattern()}")
    simplify.real_code = _real_code
    pyscopes.GlobalScope._calculate_scope_regions = _checked_scope_regions
    worder._RealFinder.is_a_class_or_function_name_in_header = _is_a_class_or_function_name_in_header
    function = pyobjectsdef.PyFunction
    function.get_param_names = _get_param_names
    function._handle_special_args = _handle_special_args
    function.get_parameters = _get_parameters
    evaluate.ScopeNameFinder.get_primary_and_pyname_at = _primary_and_pyname_at
