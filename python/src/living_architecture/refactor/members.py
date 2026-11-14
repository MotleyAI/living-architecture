"""The members a Python class declares under a name: defs, classes, class-body names and `self.` attributes."""

from __future__ import annotations

import ast
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


def member_declarations(cls: ast.ClassDef, name: str) -> list[ast.AST]:
    """Every declaration of member `name` in `cls`'s body and its methods, in source order."""
    out: list[ast.AST] = []
    for stmt in _class_level(cls.body):
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and stmt.name == name:
            out.append(stmt)
        out += [t for t in _targets(stmt) if isinstance(t, ast.Name) and t.id == name]
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
            out += _self_attributes(stmt, name)
    return sorted(out, key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0)))


def classes(tree: ast.Module) -> Iterator[ast.ClassDef]:
    yield from (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
