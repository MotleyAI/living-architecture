"""Compliance checker: report constructs that make a rename un-verifiable.

A rename's completeness can only be proven by a type checker over code the
checker can resolve. This flags the blind spots:
  - untyped-def        : a def missing param/return annotations
  - unannotated-attr   : an instance attribute assigned without a type
  - mock               : a mock/patch not bound to a spec (see mock_spec_lint)

With --attr NAME it also reports attribute accesses `x.NAME` whose receiver is
an unannotated parameter — the exact sites a rename of `.NAME` cannot be
verified against until the receiver is annotated.

Pure stdlib. Usage:
  dr-compliance [--select untyped-def,unannotated-attr,mock] [--attr NAME] PATH...
Exit 0 clean, 1 violations, 2 usage error.
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import TypeGuard

from deterministic_refactor.mock_spec_lint import check_file as _mock_check

ALL_CHECKS = ("untyped-def", "unannotated-attr", "mock")
FuncDef = (ast.FunctionDef, ast.AsyncFunctionDef)


def _is_self_attr(node: ast.AST) -> TypeGuard[ast.Attribute]:
    return (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
            and node.value.id == "self")


def _unannotated_params(fn) -> list[str]:
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
                bits.append("params " + ", ".join(miss))
            if node.returns is None:
                bits.append("return")
            if bits:
                out.append(f"{path}:{node.lineno}: untyped-def: {node.name}() missing {'; '.join(bits)}")
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
                out.append(f"{path}:{lineno}: unannotated-attr: {node.name}.{name} assigned without a type annotation")
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
            if (isinstance(sub, ast.Attribute) and sub.attr == name
                    and isinstance(sub.value, ast.Name) and sub.value.id in unann):
                out.append(f"{path}:{sub.lineno}: attr-blindspot: {sub.value.id}.{name} — "
                           f"annotate parameter '{sub.value.id}' so a rename of .{name} is verifiable")
    return out


def check_path(path: Path, selected, attr: str | None) -> list[str]:
    try:
        tree = ast.parse(path.read_text(), filename=str(path))
    except SyntaxError as exc:
        return [f"{path}:{exc.lineno or 0}: parse-error: {exc.msg}"]
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


def _iter_py(paths):
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            yield from sorted(p.rglob("*.py"))
        else:
            yield p


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="dr-compliance", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--select", default=",".join(ALL_CHECKS),
                        help=f"comma-separated checks (default: all of {','.join(ALL_CHECKS)})")
    parser.add_argument("--attr", help="also report x.ATTR accesses on unannotated receivers")
    parser.add_argument("paths", nargs="*", help="files or directories")
    args = parser.parse_args(argv)
    if not args.paths:
        parser.print_usage(sys.stderr)
        return 2
    selected = {c.strip() for c in args.select.split(",") if c.strip()}
    unknown = selected - set(ALL_CHECKS)
    if unknown:
        print(f"unknown check(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        return 2
    problems = [msg for f in _iter_py(args.paths) for msg in check_path(f, selected, args.attr)]
    for msg in problems:
        print(msg)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
