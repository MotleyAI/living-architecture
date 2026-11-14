"""The members a Python class declares under a name: defs, classes, class-body names and `self.` attributes."""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator

FunctionDef = ast.FunctionDef | ast.AsyncFunctionDef


def _targets(stmt: ast.stmt) -> list[ast.expr]:
    if isinstance(stmt, ast.Assign):
        return [t for target in stmt.targets for t in _flatten(target)]
    if isinstance(stmt, ast.AnnAssign | ast.AugAssign):
        return [stmt.target]
    return []


def _flatten(target: ast.expr) -> list[ast.expr]:
    if isinstance(target, ast.Tuple | ast.List):
        return [t for element in target.elts for t in _flatten(element)]
    return [target.value] if isinstance(target, ast.Starred) else [target]


def _self_attributes(method: FunctionDef, name: str) -> Iterator[ast.Attribute]:
    """`self.name` stores in `method`, `self` being its first parameter."""
    params = [*method.args.posonlyargs, *method.args.args]
    if not params:
        return
    first = params[0].arg
    for node in ast.walk(method):
        if (
            isinstance(node, ast.Attribute)
            and node.attr == name
            and isinstance(node.ctx, ast.Store)
            and isinstance(node.value, ast.Name)
            and node.value.id == first
        ):
            yield node


def _class_level(body: list[ast.stmt]) -> Iterator[ast.stmt]:
    """A class body's statements, those inside class-level compound blocks too, not nested scopes' bodies."""
    for stmt in body:
        yield stmt
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        for field in ("body", "orelse", "finalbody"):
            yield from _class_level(getattr(stmt, field, []))
        for handler in getattr(stmt, "handlers", []):
            yield from _class_level(handler.body)
        for case in getattr(stmt, "cases", []):
            yield from _class_level(case.body)


_BLOCK_FIELDS = frozenset({"body", "orelse", "finalbody", "handlers", "cases"})


def _bound_targets(stmt: ast.stmt) -> list[ast.expr]:
    """The names a statement binds by assignment, `for`, `with ... as` or a `type` alias."""
    targets = _targets(stmt)
    if isinstance(stmt, ast.For | ast.AsyncFor):
        targets += _flatten(stmt.target)
    if isinstance(stmt, ast.With | ast.AsyncWith):
        targets += [t for item in stmt.items if item.optional_vars is not None for t in _flatten(item.optional_vars)]
    if sys.version_info >= (3, 12) and isinstance(stmt, ast.TypeAlias):
        targets.append(stmt.name)
    return targets


_SCOPES = (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def _in_scope(node: ast.AST) -> Iterator[ast.AST]:
    """`node` and its descendants in the enclosing scope: a lambda's defaults, not its body; no comprehension."""
    yield node
    if isinstance(node, ast.Lambda):
        for default in [*node.args.defaults, *(d for d in node.args.kw_defaults if d is not None)]:
            yield from _in_scope(default)
    elif not isinstance(node, _SCOPES):
        for child in ast.iter_child_nodes(node):
            yield from _in_scope(child)


def _own_expressions(stmt: ast.stmt) -> Iterator[ast.AST]:
    """The nodes of a statement's own expressions, not of its nested blocks or scopes."""
    for field, value in ast.iter_fields(stmt):
        if field in _BLOCK_FIELDS or isinstance(stmt, FunctionDef | ast.ClassDef) and field == "body":
            continue
        for node in value if isinstance(value, list) else [value]:
            if isinstance(node, ast.AST):
                yield from _in_scope(node)
    for case in getattr(stmt, "cases", []):
        yield from _in_scope(case.pattern)
        if case.guard is not None:
            yield from _in_scope(case.guard)


def _bindings(stmt: ast.stmt, name: str) -> Iterator[ast.AST]:
    """The nodes through which a class-level statement binds `name` in the class's scope."""
    if isinstance(stmt, FunctionDef | ast.ClassDef) and stmt.name == name:
        yield stmt
    yield from (t for t in _bound_targets(stmt) if isinstance(t, ast.Name) and t.id == name)
    if isinstance(stmt, ast.Import | ast.ImportFrom):
        yield from (a for a in stmt.names if (a.asname or a.name.split(".")[0]) == name)
    yield from (h for h in getattr(stmt, "handlers", []) if h.name == name)
    for node in _own_expressions(stmt):
        if isinstance(node, ast.NamedExpr) and node.target.id == name:
            yield node.target
        elif (isinstance(node, ast.MatchAs | ast.MatchStar) and node.name == name) or (
            isinstance(node, ast.MatchMapping) and node.rest == name
        ):
            yield node


def member_declarations(cls: ast.ClassDef, name: str) -> list[ast.AST]:
    """Every declaration of member `name` in `cls`'s body and its methods, in source order."""
    out: list[ast.AST] = []
    for stmt in _class_level(cls.body):
        out += _bindings(stmt, name)
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
            out += _self_attributes(stmt, name)
    return sorted(out, key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0)))


def classes(tree: ast.Module) -> Iterator[ast.ClassDef]:
    yield from (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
