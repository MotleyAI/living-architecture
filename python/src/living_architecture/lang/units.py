"""Python units under a source root: dotted modules, packages (dirs with `__init__.py`) and import targets."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path
from typing import TypeAlias

from pydantic import BaseModel

_INIT_PY = "__init__.py"
_Aliases: TypeAlias = tuple[set[str], set[str]]


class SourceModule(BaseModel):
    """A source file as a dotted module (`is_package`: it is a package's `__init__.py`)."""

    module: str
    path: Path
    is_package: bool


def unit_exists(source_root: Path, dotted: str) -> bool:
    """A package directory or a module file named by the dotted path."""
    base = source_root / Path(*dotted.split("."))
    return (base / _INIT_PY).is_file() or base.with_suffix(".py").is_file()


def top_level_units(source_root: Path, root_package: str) -> set[str]:
    """Immediate children of the root package: subpackages and loose modules."""
    units: set[str] = set()
    for child in (source_root / root_package).iterdir():
        if child.name == "__pycache__":
            continue
        if child.is_dir() and (child / _INIT_PY).is_file():
            units.add(f"{root_package}.{child.name}")
        elif child.is_file() and child.suffix == ".py" and child.name != _INIT_PY:
            units.add(f"{root_package}.{child.stem}")
    return units


def source_modules(source_root: Path, root_package: str) -> list[SourceModule]:
    """Every module under the root package in path order; the root `__init__.py` is exempt."""
    out: list[SourceModule] = []
    for py in sorted((source_root / root_package).rglob("*.py")):
        rel = py.relative_to(source_root)
        if "__pycache__" in rel.parts:
            continue
        parts = list(rel.with_suffix("").parts)
        is_package = parts[-1] == "__init__"
        if is_package:
            parts = parts[:-1]
        if parts == [root_package]:
            continue
        out.append(SourceModule(module=".".join(parts), path=py, is_package=is_package))
    return out


def _args(args: ast.arguments) -> list[ast.arg]:
    params = [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]
    return [a for a in params if a is not None]


def _header_parts(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda | ast.ClassDef) -> list[ast.AST]:
    """The parts of a nested scope evaluated in the enclosing scope."""
    if isinstance(node, ast.ClassDef):
        return [*node.decorator_list, *node.bases, *node.keywords]
    defaults: list[ast.AST] = [*node.args.defaults, *(d for d in node.args.kw_defaults if d is not None)]
    if isinstance(node, ast.Lambda):
        return defaults
    annotations = [a.annotation for a in _args(node.args) if a.annotation is not None]
    return [*node.decorator_list, *defaults, *annotations, *([node.returns] if node.returns else [])]


def _scope_nodes(body: list[ast.stmt]) -> Iterator[ast.AST]:
    """Nodes binding names in the scope owning `body`; comprehension targets are local to the comprehension."""
    stack: list[ast.AST] = list(body)
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            stack.extend(_header_parts(node))
        elif isinstance(node, ast.comprehension):
            stack.extend([node.iter, *node.ifs])
        else:
            stack.extend(ast.iter_child_nodes(node))


def _bound_names(node: ast.AST) -> set[str]:
    """Names a non-import node binds in its scope."""
    if isinstance(node, ast.Name):
        return {node.id} if isinstance(node.ctx, (ast.Store, ast.Del)) else set()
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)):
        return {node.name} if node.name else set()
    if isinstance(node, ast.MatchMapping):
        return {node.rest} if node.rest else set()
    return set()


def _import_bindings(node: ast.Import, modules: set[str], rebound: set[str]) -> None:
    for a in node.names:
        if a.name == "typing":
            modules.add(a.asname or "typing")
        else:
            rebound.add(a.asname or a.name.split(".")[0])


def _import_from_bindings(node: ast.ImportFrom, flags: set[str], rebound: set[str]) -> None:
    from_typing = node.level == 0 and node.module == "typing"
    for a in node.names:
        if from_typing and a.name == "TYPE_CHECKING":
            flags.add(a.asname or "TYPE_CHECKING")
        else:
            rebound.add(a.asname or a.name)


def _scope_aliases(body: list[ast.stmt], outer: _Aliases, params: set[str], poisoned: set[str]) -> _Aliases:
    """(typing, typing.TYPE_CHECKING) aliases visible in a scope; any local binding shadows the outer ones."""
    modules: set[str] = set()
    flags: set[str] = set()
    other = set(params)
    for node in _scope_nodes(body):
        if isinstance(node, ast.Import):
            _import_bindings(node, modules, other)
        elif isinstance(node, ast.ImportFrom):
            _import_from_bindings(node, flags, other)
        else:
            other |= _bound_names(node)
    local = modules | flags | other
    return (
        ((outer[0] - local) | (modules - flags - other)) - poisoned,
        ((outer[1] - local) | (flags - modules - other)) - poisoned,
    )


def _is_type_checking_test(test: ast.expr, modules: set[str], flags: set[str]) -> bool:
    if isinstance(test, ast.Name):
        return test.id in flags
    return (
        isinstance(test, ast.Attribute)
        and test.attr == "TYPE_CHECKING"
        and isinstance(test.value, ast.Name)
        and test.value.id in modules
    )


def _import_from_base(node: ast.ImportFrom, module_parts: list[str], is_package: bool) -> str:
    if node.level == 0:
        return node.module or ""
    ctx = module_parts if is_package else module_parts[:-1]
    ctx = ctx[: len(ctx) - (node.level - 1)]
    return ".".join(ctx + ([node.module] if node.module else []))


def _stmt_import_targets(node: ast.AST, module_parts: list[str], is_package: bool) -> set[str]:
    if isinstance(node, ast.Import):
        return {alias.name for alias in node.names}
    if isinstance(node, ast.ImportFrom):
        base = _import_from_base(node, module_parts, is_package)
        if not base:
            return set()
        return {base, *(f"{base}.{alias.name}" for alias in node.names)}
    return set()


def import_targets(module: SourceModule) -> set[str]:
    """Absolute dotted targets of runtime imports; typing.TYPE_CHECKING-guarded bodies excluded.

    Guard names resolve lexically; a name declared `global`/`nonlocal` anywhere is never a guard.
    """
    tree = ast.parse(module.path.read_text(encoding="utf-8"))
    poisoned = {n for node in ast.walk(tree) if isinstance(node, (ast.Global, ast.Nonlocal)) for n in node.names}
    root = _scope_aliases(tree.body, (set(), set()), set(), poisoned)
    module_parts = module.module.split(".")
    targets: set[str] = set()
    # (node, aliases where it runs, aliases a function defined there closes over: class bodies are skipped)
    stack: list[tuple[ast.AST, _Aliases, _Aliases]] = [(n, root, root) for n in tree.body]
    while stack:
        node, here, closure = stack.pop()
        if isinstance(node, ast.If) and _is_type_checking_test(node.test, *here):
            stack.extend((n, here, closure) for n in node.orelse)
            continue
        targets |= _stmt_import_targets(node, module_parts, module.is_package)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            inner = _scope_aliases(node.body, closure, {a.arg for a in _args(node.args)}, poisoned)
            stack.extend((n, inner, inner) for n in node.body)
        elif isinstance(node, ast.ClassDef):
            body_aliases = _scope_aliases(node.body, closure, set(), poisoned)
            stack.extend((n, body_aliases, closure) for n in node.body)
        else:
            stack.extend((n, here, closure) for n in ast.iter_child_nodes(node))
    return targets
