"""Python units under a source root: dotted modules, packages (dirs with `__init__.py`) and import targets."""

from __future__ import annotations

import ast
from pathlib import Path

from pydantic import BaseModel

_INIT_PY = "__init__.py"


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


def _param_names(args: ast.arguments) -> set[str]:
    params = [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]
    return {a.arg for a in params if a is not None}


def _assignment_targets(node: ast.AST) -> list[ast.expr]:
    if isinstance(node, (ast.Assign, ast.Delete)):
        return node.targets
    if isinstance(node, (ast.AugAssign, ast.AnnAssign, ast.For, ast.AsyncFor, ast.NamedExpr)):
        return [node.target]
    if isinstance(node, ast.comprehension):
        return [node.target]
    if isinstance(node, ast.withitem) and node.optional_vars is not None:
        return [node.optional_vars]
    return []


def _bound_names(node: ast.AST) -> set[str]:
    """Names (re)bound by a non-import node — used to invalidate typing aliases."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return {node.name, *_param_names(node.args)}
    if isinstance(node, ast.Lambda):
        return _param_names(node.args)
    if isinstance(node, ast.ClassDef):
        return {node.name}
    if isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)):
        return {node.name} if node.name else set()
    if isinstance(node, ast.MatchMapping):
        return {node.rest} if node.rest else set()
    return {
        sub.id
        for t in _assignment_targets(node)
        for sub in ast.walk(t)
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, (ast.Store, ast.Del))
    }


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


def _typing_bindings(tree: ast.Module) -> tuple[set[str], set[str]]:
    """Names bound to typing / typing.TYPE_CHECKING, minus names rebound by anything else."""
    modules: set[str] = set()
    flags: set[str] = set()
    rebound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            _import_bindings(node, modules, rebound)
        elif isinstance(node, ast.ImportFrom):
            _import_from_bindings(node, flags, rebound)
        else:
            rebound |= _bound_names(node)
    return modules - rebound, flags - rebound


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
    """Absolute dotted targets of runtime imports; typing.TYPE_CHECKING-guarded bodies excluded."""
    tree = ast.parse(module.path.read_text(encoding="utf-8"))
    modules, flags = _typing_bindings(tree)
    module_parts = module.module.split(".")
    targets: set[str] = set()
    stack: list[ast.AST] = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, ast.If) and _is_type_checking_test(node.test, modules, flags):
            stack.extend(node.orelse)
            continue
        targets |= _stmt_import_targets(node, module_parts, module.is_package)
        stack.extend(ast.iter_child_nodes(node))
    return targets
