"""`--symbol Q`: a declaration located by its path inside a Python file (`Class.method`, `func.<locals>.inner`,
`func(param)`, `Alias['value']`); declarations in one scope are one symbol, as the checker binds them. A wildcard path
(`*.<locals>.NAME`, `Scope.*.<locals>.NAME`) names every local NAME of the functions under the file or scope."""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Callable, Iterator

from pydantic import BaseModel, ConfigDict

from living_architecture.contract import message
from living_architecture.refactor.members import bound_targets, receiver_stores
from living_architecture.refactor.python_source import SourceFile, every_parameter

LOCALS = "<locals>"
WILDCARD = "*"
_PATH = re.compile(r"(?P<path>[^()\[\]]+)(?:\((?P<param>[^()]+)\))?(?:\[(?P<quote>['\"])(?P<value>.*)(?P=quote)\])?")
_AS_NAME = re.compile(r"\bas\s+(\w+)")
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
    declarations of its symbol with the offset of each one's name, and whether it is a top-level declaration of the
    module."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    offset: int
    nodes: tuple[ast.AST, ...]
    top_level: bool
    offsets: tuple[int, ...] = ()


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


def names_literal(node: ast.expr) -> bool:
    """`node` names `typing.Literal` (bare or qualified)."""
    return (isinstance(node, ast.Name) and node.id == "Literal") or (isinstance(node, ast.Attribute) and node.attr == "Literal")


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
        yield from _statement_bindings(source, stmt)


def _statement_bindings(source: SourceFile, stmt: ast.stmt) -> Iterator[Declaration]:
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        span = source.name_span(stmt)
        if span is not None:
            yield stmt.name, span[0], stmt
    elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
        for alias in (a for a in stmt.names if a.name != "*"):
            name, offset = _alias_name(source, alias)
            yield name, offset, alias
    for target in bound_targets(stmt):
        if isinstance(target, ast.Name):
            yield target.id, source.span(target)[0], target


def _self_attributes(source: SourceFile, cls: ast.ClassDef) -> Iterator[Declaration]:
    """Each `self.NAME` a method of `cls` assigns, by its first parameter."""
    for method in (s for s in _statements(cls.body) if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))):
        for target in receiver_stores(method):
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
    groups = _walk(source, module, path.segments, unresolved)
    if len(groups) > 1:
        sites = ", ".join(f"{shown}:{source.line(g[0][1])}" for g in groups)
        raise LocatorError(message("refactor.symbol-ambiguous", path=shown, symbol=raw, candidates=sites))
    group = groups[0]
    if path.param is not None:
        located = _parameter(source, group, path.param, unresolved)
        if path.value is not None:
            return _literal_member(source, [(path.param, located.offset, located.nodes[0])], path.value, unresolved)
        return located
    if path.value is not None:
        return _literal_member(source, group, path.value, unresolved)
    return _group_located(group, top_level=len(path.segments) == 1)


def _group_located(group: list[Declaration], *, top_level: bool = False) -> Located:
    return Located(offset=group[0][1], nodes=tuple(n for _, _, n in group), top_level=top_level,
                   offsets=tuple(offset for _, offset, _ in group))


def wildcard_parts(raw: str) -> tuple[tuple[str, ...], str] | None:
    """A wildcard path's scope segments (none: the file) and local name; None for any other path."""
    path = SymbolPath.parse(raw)
    if path is None or path.param is not None or path.value is not None or len(path.segments) < 3:
        return None
    *scope, star, step, name = path.segments
    if (star, step) != (WILDCARD, LOCALS) or WILDCARD in (*scope, name) or name == LOCALS:
        return None
    return tuple(scope), name


def is_wildcard(raw: str | None) -> bool:
    return raw is not None and wildcard_parts(raw) is not None


def wildcard_refused(shown: str, raw: str) -> LocatorError:
    return LocatorError(message("refactor.symbol-wildcard", path=shown, symbol=raw))


def _nested_functions(node: ast.AST) -> Iterator[Function]:
    """Every function nested at any depth inside `node`."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield child
        yield from _nested_functions(child)


def locate_all(source: SourceFile, raw: str, shown: str) -> list[Located]:
    """Every local the wildcard path `raw` names in `source`, in source order; LocatorError when it names none."""
    parts = wildcard_parts(raw)
    assert parts is not None
    segments, name = parts

    def unresolved(names: set[str]) -> LocatorError:
        candidates = ", ".join(sorted(names))
        return LocatorError(message("refactor.symbol-unresolved", path=shown, symbol=raw, candidates=candidates))

    if source.tree is None:
        raise unresolved(set())
    scopes = [Scope(kind="module", node=source.tree)]
    if segments:
        scopes = [s for g in _walk(source, scopes[0], segments, unresolved) for s in _opened(g)]
    found: dict[int, Located] = {}
    for function in (f for scope in scopes for f in _nested_functions(scope.node)):
        group = [d for d in _declarations(source, Scope(kind="function", node=function)) if d[0] == name]
        if group:
            found[group[0][1]] = _group_located(group)
    if not found:
        raise unresolved({declared for scope in scopes for declared, _, _ in _declarations(source, scope)})
    return [found[offset] for offset in sorted(found)]


def _walk(source: SourceFile, module: Scope, segments: tuple[str, ...], unresolved: Unresolved) -> list[list[Declaration]]:
    """The symbols (declaration groups) the segments reach from the module."""
    scopes, i = [module], 0
    while True:
        groups = [g for s in scopes if (g := [d for d in _declarations(source, s) if d[0] == segments[i]])]
        if not groups:
            raise unresolved({name for s in scopes for name, _, _ in _declarations(source, s)})
        i += 1
        if i == len(segments):
            return groups
        step = segments[i]
        if step == LOCALS:
            i += 1
        scopes = [inner for g in groups for _, _, node in g if (inner := _inner(node, step if step == LOCALS else ""))]
        if not scopes:
            raise unresolved({name for g in groups for s in _opened(g) for name, _, _ in _declarations(source, s)})


def _parameter(source: SourceFile, group: list[Declaration], name: str, unresolved: Unresolved) -> Located:
    functions = [n for _, _, n in group if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    params = [a for fn in functions for a in every_parameter(fn.args)]
    arg = next((a for a in params if a.arg == name), None)
    span = source.name_span(arg) if arg is not None else None
    if arg is None or span is None:
        raise unresolved({a.arg for a in params})
    return Located(offset=span[0], nodes=(arg,), top_level=False, offsets=(span[0],))


def _literal_member(source: SourceFile, group: list[Declaration], value: str, unresolved: Unresolved) -> Located:
    """The string `value` inside a `Literal[...]` of the declaration's annotation or alias body."""
    strings: list[tuple[str, ast.Constant]] = []
    for _, _, node in group:
        holder = _literal_holder(source, node)
        if holder is not None:
            literals = (n for n in ast.walk(holder) if isinstance(n, ast.Subscript) and names_literal(n.value))
            strings += [
                (n.value, n) for lit in literals for n in ast.walk(lit.slice) if isinstance(n, ast.Constant) and isinstance(n.value, str)
            ]
    found = next((string for text, string in strings if text == value), None)
    if found is None:
        raise unresolved({text for text, _ in strings})
    return Located(offset=source.span(found)[0], nodes=(found,), top_level=False, offsets=(source.span(found)[0],))


def _literal_holder(source: SourceFile, node: ast.AST) -> ast.expr | None:
    """The annotation or alias body of a declaration that may hold a literal type."""
    parent = _statement_of(source, node)
    if isinstance(parent, ast.AnnAssign):
        annotation = parent.annotation
        if (isinstance(annotation, ast.Name) and annotation.id == "TypeAlias") or (
            isinstance(annotation, ast.Attribute) and annotation.attr == "TypeAlias"
        ):
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
    for stmt in source.nodes:
        if isinstance(stmt, ast.stmt) and any(child is node for child in ast.walk(stmt)) and not isinstance(
            stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, *_COMPOUND)
        ):
            return stmt
    return None


def declaration_scope(source: SourceFile, name: str, line: int) -> tuple[ast.AST, ast.AST] | None:
    """The scope declaring `name` on `line` (a class's `self.` attributes in the class) and the declaring node."""
    if source.tree is None:
        return None
    stack: list[Scope] = [Scope(kind="module", node=source.tree)]
    while stack:
        scope = stack.pop()
        for found, offset, node in _declarations(source, scope):
            if found == name and source.line(offset) == line:
                return scope.node, node
        stack += _child_scopes(scope.node)
    return None


def _child_scopes(node: ast.AST) -> list[Scope]:
    """The classes and functions directly nested in `node`'s body, not inside one another."""
    out: list[Scope] = []
    pending = list(ast.iter_child_nodes(node))
    while pending:
        child = pending.pop()
        if isinstance(child, ast.ClassDef):
            out.append(Scope(kind="class", node=child))
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(Scope(kind="function", node=child))
        else:
            pending += ast.iter_child_nodes(child)
    return out


def declared_scopes(source: SourceFile) -> Iterator[tuple[ast.AST, list[Declaration]]]:
    """Every module, class and function scope of `source` with the declarations a path reaches in it."""
    if source.tree is None:
        return
    stack: list[Scope] = [Scope(kind="module", node=source.tree)]
    while stack:
        scope = stack.pop()
        yield scope.node, _declarations(source, scope)
        stack += _child_scopes(scope.node)


def declared_paths(source: SourceFile) -> Iterator[tuple[str, list[Declaration]]]:
    """Every path of `source` with the declarations it reaches in one scope; a path given twice names two symbols."""
    if source.tree is not None:
        yield from _scope_paths(source, Scope(kind="module", node=source.tree), "")


def _scope_paths(source: SourceFile, scope: Scope, prefix: str) -> Iterator[tuple[str, list[Declaration]]]:
    groups: dict[str, list[Declaration]] = {}
    for declaration in _declarations(source, scope):
        groups.setdefault(declaration[0], []).append(declaration)
    for name, group in groups.items():
        path = prefix + name
        yield path, group
        parameters: set[str] = set()
        for _, _, node in group:
            if isinstance(node, ast.ClassDef):
                yield from _scope_paths(source, Scope(kind="class", node=node), f"{path}.")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for arg in every_parameter(node.args):
                    span = source.name_span(arg)
                    if span is not None and arg.arg not in parameters:
                        parameters.add(arg.arg)
                        yield f"{path}({arg.arg})", [(arg.arg, span[0], arg)]
                yield from _scope_paths(source, Scope(kind="function", node=node), f"{path}.{LOCALS}.")
