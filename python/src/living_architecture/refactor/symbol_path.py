"""`--symbol Q`: a declaration located by its path inside a Python file (`Class.method`, `func.<locals>.inner`,
`func(param)`, `Alias['value']`); declarations in one scope are one symbol, as the checker binds them."""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Callable, Iterator

from pydantic import BaseModel, ConfigDict

from living_architecture.contract import message
from living_architecture.refactor.python_source import SourceFile

LOCALS = "<locals>"
_PATH = re.compile(r"(?P<path>[^()\[\]]+?)(?:\((?P<param>[^()]+)\))?(?:\[(?P<quote>['\"])(?P<value>.*)(?P=quote)\])?")
_AS_NAME = re.compile(r"\s+as\s+(\w+)")
_COMPOUND = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match, ast.TryStar)
Function = ast.FunctionDef | ast.AsyncFunctionDef
Declaration = tuple[str, int, ast.AST]
Unresolved = Callable[[set[str]], "LocatorError"]


class LocatorError(Exception):
    """The path names no declaration, or more than one symbol; the message is user-facing (exit 2)."""


class SymbolPath(BaseModel):
    """A parsed `--symbol`: its segments, an optional trailing parameter and an optional literal member value."""

    model_config = ConfigDict(frozen=True)

    segments: tuple[str, ...]
    param: str | None = None
    value: str | None = None

    @staticmethod
    def parse(raw: str) -> SymbolPath | None:
        m = _PATH.fullmatch(raw.strip())
        if m is None:
            return None
        segments = tuple(s.strip() for s in m.group("path").split("."))
        if not all(segments) or segments[0] == LOCALS or segments[-1] == LOCALS:
            return None
        param = m.group("param")
        return SymbolPath(segments=segments, param=param.strip() if param else None, value=m.group("value"))


class Scope(BaseModel):
    """A module, class or function body whose bindings a segment looks up."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    kind: str
    node: ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef


class Located(BaseModel):
    """What a path names: the character offset of the declaration's name (or the literal member's string), the
    declarations of its symbol, and whether it is a top-level declaration of the module."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    offset: int
    nodes: tuple[ast.AST, ...]
    top_level: bool


def _statements(body: list[ast.stmt]) -> Iterator[ast.stmt]:
    """The statements of a body, compound statements entered, nested defs and classes not."""
    for stmt in body:
        yield stmt
        if isinstance(stmt, ast.Match):
            for case in stmt.cases:
                yield from _statements(case.body)
        elif isinstance(stmt, _COMPOUND):
            for field in ("body", "orelse", "finalbody"):
                yield from _statements(getattr(stmt, field, []))
            for handler in getattr(stmt, "handlers", []):
                yield from _statements(handler.body)


def _targets(stmt: ast.stmt) -> Iterator[ast.expr]:
    """The expressions an assignment statement binds, tuples and lists unpacked."""
    found = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target] if isinstance(stmt, ast.AnnAssign) else []
    stack = list(found)
    while stack:
        node = stack.pop(0)
        if isinstance(node, (ast.Tuple, ast.List)):
            stack[:0] = node.elts
        elif isinstance(node, ast.Starred):
            stack.insert(0, node.value)
        else:
            yield node


def _alias_name(source: SourceFile, alias: ast.alias) -> tuple[str, int]:
    """The name an import alias binds and its offset."""
    start = source.offset(alias.lineno, alias.col_offset)
    if alias.asname is None:
        return alias.name.split(".")[0], start
    m = _AS_NAME.search(source.text, start + len(alias.name))
    return alias.asname, m.start(1) if m else start


def _bindings(source: SourceFile, body: list[ast.stmt]) -> Iterator[Declaration]:
    """Each name a body binds: its offset and declaring node."""
    for stmt in _statements(body):
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            span = source.name_span(stmt)
            if span is not None:
                yield stmt.name, span[0], stmt
        elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
            for alias in stmt.names:
                if alias.name != "*":
                    name, offset = _alias_name(source, alias)
                    yield name, offset, alias
        if sys.version_info >= (3, 12) and isinstance(stmt, ast.TypeAlias):
            yield stmt.name.id, source.span(stmt.name)[0], stmt.name
        for target in _targets(stmt):
            if isinstance(target, ast.Name):
                yield target.id, source.span(target)[0], target


def _self_attributes(source: SourceFile, cls: ast.ClassDef) -> Iterator[Declaration]:
    """Each `self.NAME` a method of `cls` assigns, by its first parameter."""
    for method in (s for s in _statements(cls.body) if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))):
        params = [*method.args.posonlyargs, *method.args.args]
        if not params:
            continue
        receiver = params[0].arg
        for node in ast.walk(method):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
            for target in targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == receiver:
                    span = source.name_span(target)
                    if span is not None:
                        yield target.attr, span[0], target


def _declarations(source: SourceFile, scope: Scope) -> list[Declaration]:
    body = scope.node.body
    found = list(_bindings(source, body))
    if isinstance(scope.node, ast.ClassDef):
        declared = {name for name, _, _ in found}
        found += [d for d in _self_attributes(source, scope.node) if d[0] not in declared]
    return sorted(found, key=lambda d: d[1])


def _inner(node: ast.AST, step: str) -> Scope | None:
    """The scope a declaration opens for the next step: a class for a member, a function for `<locals>`."""
    if step == LOCALS:
        return Scope(kind="function", node=node) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else None
    return Scope(kind="class", node=node) if isinstance(node, ast.ClassDef) else None


def _opened(group: list[Declaration]) -> list[Scope]:
    """Every scope a group's declarations open, whatever the next step."""
    return [s for _, _, node in group for step in (LOCALS, "") if (s := _inner(node, step)) is not None]


def locate(source: SourceFile, raw: str, shown: str) -> Located:
    """The declaration `raw` names in `source`; LocatorError when it names none or more than one symbol."""
    path = SymbolPath.parse(raw)

    def unresolved(names: set[str]) -> LocatorError:
        candidates = ", ".join(sorted(names))
        return LocatorError(message("refactor.symbol-unresolved", path=shown, symbol=raw, candidates=candidates))

    if source.tree is None:
        raise unresolved(set())
    module = Scope(kind="module", node=source.tree)
    if path is None:
        raise unresolved({name for name, _, _ in _declarations(source, module)})
    scopes, groups, segments, i = [module], list[list[Declaration]](), path.segments, 0
    while True:
        groups = [g for s in scopes if (g := [d for d in _declarations(source, s) if d[0] == segments[i]])]
        if not groups:
            raise unresolved({name for s in scopes for name, _, _ in _declarations(source, s)})
        i += 1
        if i == len(segments):
            break
        step = segments[i]
        if step == LOCALS:
            i += 1
        scopes = [inner for g in groups for _, _, node in g if (inner := _inner(node, step if step == LOCALS else ""))]
        if not scopes:
            raise unresolved({name for g in groups for s in _opened(g) for name, _, _ in _declarations(source, s)})
    if len(groups) > 1:
        sites = ", ".join(f"{shown}:{source.line(g[0][1])}" for g in groups)
        raise LocatorError(message("refactor.symbol-ambiguous", path=shown, symbol=raw, candidates=sites))
    group = groups[0]
    if path.param is not None:
        return _parameter(source, group, path.param, unresolved)
    if path.value is not None:
        return _literal_member(source, group, path.value, unresolved)
    return Located(offset=group[0][1], nodes=tuple(n for _, _, n in group), top_level=len(segments) == 1)


def _parameter(source: SourceFile, group: list[Declaration], name: str, unresolved: Unresolved) -> Located:
    functions = [n for _, _, n in group if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    params = [a for fn in functions for a in _every_parameter(fn)]
    arg = next((a for a in params if a.arg == name), None)
    span = source.name_span(arg) if arg is not None else None
    if arg is None or span is None:
        raise unresolved({a.arg for a in params})
    return Located(offset=span[0], nodes=(arg,), top_level=False)


def _every_parameter(fn: Function) -> list[ast.arg]:
    a = fn.args
    return [*a.posonlyargs, *a.args, *([a.vararg] if a.vararg else []), *a.kwonlyargs, *([a.kwarg] if a.kwarg else [])]


def _literal_member(source: SourceFile, group: list[Declaration], value: str, unresolved: Unresolved) -> Located:
    """The string `value` inside a `Literal[...]` of the declaration's annotation or alias body."""
    strings: list[tuple[str, ast.Constant]] = []
    for _, _, node in group:
        holder = _literal_holder(source, node)
        if holder is not None:
            strings += [(n.value, n) for n in ast.walk(holder) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    found = next((string for text, string in strings if text == value), None)
    if found is None:
        raise unresolved({text for text, _ in strings})
    return Located(offset=source.span(found)[0], nodes=(found,), top_level=False)


def _literal_holder(source: SourceFile, node: ast.AST) -> ast.expr | None:
    """The annotation or alias body of a declaration that may hold a literal type."""
    parent = _statement_of(source, node)
    if isinstance(parent, ast.AnnAssign):
        if isinstance(parent.annotation, ast.Name) and parent.annotation.id == "TypeAlias":
            return parent.value
        return parent.annotation
    if isinstance(parent, ast.Assign):
        return parent.value
    if isinstance(node, ast.arg):
        return node.annotation
    if sys.version_info >= (3, 12) and isinstance(parent, ast.TypeAlias):
        return parent.value
    return None


def _statement_of(source: SourceFile, node: ast.AST) -> ast.stmt | None:
    assert source.tree is not None
    for stmt in ast.walk(source.tree):
        if isinstance(stmt, ast.stmt) and any(child is node for child in ast.walk(stmt)) and not isinstance(
            stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, *_COMPOUND)
        ):
            return stmt
    return None
