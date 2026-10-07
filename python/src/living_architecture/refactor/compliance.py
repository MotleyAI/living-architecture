"""`dr-compliance`: report constructs that make a rename un-verifiable.

A rename's completeness can only be proven by a type checker over code the checker can resolve. This flags
the blind spots: untyped-def, unannotated-attr, and mock (a double not bound to a spec). With an attribute
name it also reports `x.NAME` accesses whose receiver is an unannotated parameter.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import TypeGuard

from living_architecture.contract import language, message
from living_architecture.refactor.mock_spec_lint import check_file as _mock_check
from living_architecture.refactor.routing import RoutingError, compliance_selection, run_split, split

ALL_CHECKS = tuple(language("python")["compliance_checks"])
FuncDef = (ast.FunctionDef, ast.AsyncFunctionDef)


def _is_self_attr(node: ast.AST) -> TypeGuard[ast.Attribute]:
    return isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self"


def _unannotated_params(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    a = fn.args
    out: list[str] = []
    for i, arg in enumerate(a.posonlyargs + a.args):
        if i == 0 and arg.arg in ("self", "cls"):
            continue
        if arg.annotation is None:
            out.append(arg.arg)
    out += [arg.arg for arg in a.kwonlyargs if arg.annotation is None]
    if a.vararg and a.vararg.annotation is None:
        out.append("*" + a.vararg.arg)
    if a.kwarg and a.kwarg.annotation is None:
        out.append("**" + a.kwarg.arg)
    return out


def _check_untyped_defs(tree: ast.AST, path: Path) -> list[str]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, FuncDef):
            miss = _unannotated_params(node)
            bits = []
            if miss:
                bits.append(message("compliance.untyped-params", params=", ".join(miss)))
            if node.returns is None:
                bits.append(message("compliance.untyped-return"))
            if bits:
                out.append(
                    message("compliance.untyped-def", path=str(path), line=node.lineno, name=node.name, missing="; ".join(bits))
                )
    return out


def _check_unannotated_attrs(tree: ast.AST, path: Path) -> list[str]:
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        annotated: set[str] = set()
        assigned: dict[str, int] = {}
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                annotated.add(stmt.target.id)
        for method in (s for s in node.body if isinstance(s, FuncDef)):
            for sub in ast.walk(method):
                if isinstance(sub, ast.AnnAssign) and _is_self_attr(sub.target):
                    annotated.add(sub.target.attr)
                elif isinstance(sub, ast.Assign):
                    for tgt in sub.targets:
                        if _is_self_attr(tgt):
                            assigned.setdefault(tgt.attr, sub.lineno)
        for name, lineno in assigned.items():
            if name not in annotated:
                out.append(message("compliance.unannotated-attr", path=str(path), line=lineno, cls=node.name, attr=name))
    return out


def _check_attr_blindspots(tree: ast.AST, path: Path, name: str) -> list[str]:
    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, FuncDef):
            continue
        unann = set(_unannotated_params(fn))
        if not unann:
            continue
        for sub in ast.walk(fn):
            if (
                isinstance(sub, ast.Attribute)
                and sub.attr == name
                and isinstance(sub.value, ast.Name)
                and sub.value.id in unann
            ):
                out.append(
                    message("compliance.attr-blindspot", path=str(path), line=sub.lineno, receiver=sub.value.id, attr=name)
                )
    return out


def check_path(path: Path, selected: set[str], attr: str | None) -> list[str]:
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError as exc:
        return [message("compliance.parse-error", path=str(path), line=exc.lineno or 0, error=exc.msg)]
    out: list[str] = []
    if "untyped-def" in selected:
        out += _check_untyped_defs(tree, path)
    if "unannotated-attr" in selected:
        out += _check_unannotated_attrs(tree, path)
    if "mock" in selected:
        out += _mock_check(path)
    if attr:
        out += _check_attr_blindspots(tree, path, attr)
    return sorted(out)


def _check_native(paths: list[str], selected: set[str], attr: str | None) -> int:
    problems = [msg for f in paths for msg in check_path(Path(f), selected, attr)]
    for msg in problems:
        print(msg)
    return 1 if problems else 0


def run_compliance(*, paths: list[str], select: str | None, attr: str | None) -> int:
    """`dr-compliance`: each file with its language's checks, the other language's in its twin."""
    try:
        selected = compliance_selection(select)
        groups = split("dr-compliance", paths, Path.cwd())
    except RoutingError as exc:
        print(exc, file=sys.stderr)
        return 2
    options = [*(["--select", select] if select is not None else []), *(["--attr", attr] if attr is not None else [])]
    own = set(ALL_CHECKS) if selected is None else selected & set(ALL_CHECKS)
    return run_split("dr-compliance", groups, lambda files: [*options, "--", *files], lambda files: _check_native(files, own, attr))
