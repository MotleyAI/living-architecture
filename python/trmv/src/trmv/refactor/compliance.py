"""`trmv-compliance`: report constructs that make a rename un-verifiable.

A rename's completeness can only be proven by a type checker over code the checker can resolve. This flags
the blind spots: untyped-def, unannotated-attr, explicit-any (a reference to `typing.Any`), mock (a double not bound
to a spec), rope-walk (a file rope's walker cannot cover) and, given an attribute name, attr-blindspot (`x.NAME`
accesses) and string-blindspot (accesses naming NAME by a string) whose receiver basedpyright types as `Unknown` or
`Any`.
"""

from __future__ import annotations

import ast
import sys
from collections import defaultdict
from pathlib import Path
from typing import TypeGuard

from trmv.contract import language, message
from trmv.lang import LanguageServerError
from trmv.refactor.explicit_any import check_explicit_any
from trmv.refactor.index_cache import IndexCache
from trmv.refactor.member_scan import MemberScan, probe_round
from trmv.refactor.mock_spec_lint import mock_findings
from trmv.refactor.occurrence_index import RunIndex, ServerSession
from trmv.refactor.outcomes import blindspot_text
from trmv.refactor.python_source import SourceFile
from trmv.refactor.rope_patches import apply_rope_patches, walk_gap_line
from trmv.refactor.routing import RoutingError, compliance_selection, run_split, split

apply_rope_patches()

ALL_CHECKS = tuple(language("python")["compliance_checks"])
ATTR_CHECKS = ("attr-blindspot", "string-blindspot")
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


def _check_untyped_defs(tree: ast.AST, path: Path) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, FuncDef):
            miss = _unannotated_params(node)
            bits = []
            if miss:
                bits.append(message("compliance.untyped-params", params=", ".join(miss)))
            if node.returns is None:
                bits.append(message("compliance.untyped-return"))
            if bits:
                text = message("compliance.untyped-def", path=str(path), line=node.lineno, name=node.name, missing="; ".join(bits))
                out.append((node.lineno, text))
    return out


def _self_attrs(node: ast.ClassDef) -> tuple[set[str], dict[str, int]]:
    """The `self.x` attributes the class's methods annotate, and the first line assigning each."""
    annotated: set[str] = set()
    assigned: dict[str, int] = {}
    for method in (s for s in node.body if isinstance(s, FuncDef)):
        for sub in ast.walk(method):
            if isinstance(sub, ast.AnnAssign) and _is_self_attr(sub.target):
                annotated.add(sub.target.attr)
            elif isinstance(sub, ast.Assign):
                for tgt in filter(_is_self_attr, sub.targets):
                    assigned.setdefault(tgt.attr, sub.lineno)
    return annotated, assigned


def _check_unannotated_attrs(tree: ast.AST, path: Path) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        annotated, assigned = _self_attrs(node)
        annotated |= {s.target.id for s in node.body if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)}
        out += [
            (lineno, message("compliance.unannotated-attr", path=str(path), line=lineno, cls=node.name, attr=name))
            for name, lineno in assigned.items()
            if name not in annotated
        ]
    return out


def _read_sources(paths: list[Path]) -> dict[Path, tuple[str, SourceFile]]:
    """Each distinct file once, keyed by its resolved path, with the path as given."""
    sources: dict[Path, tuple[str, SourceFile]] = {}
    for path in paths:
        resolved = path.resolve()
        if resolved not in sources:
            with open(resolved, encoding="utf-8", newline="") as fh:
                sources[resolved] = (str(path), SourceFile(resolved, fh.read()))
    return sources


def _outside(path: Path) -> SourceFile | None:
    """A file outside the checked ones (a callee's declaration)."""
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            return SourceFile(path, fh.read())
    except (OSError, UnicodeDecodeError):
        return None


def _blindspots(paths: list[Path], names: list[str], workspace: Path, checks: set[str]) -> dict[str, list[tuple[int, str]]]:
    """Each file's blind spots of `checks`: receivers of `.NAME` (for every name) and string-named objects
    basedpyright types as Unknown or Any, and string-member calls whose callee it cannot resolve, in line, column and
    name order, keyed by the path as given."""
    sources = _read_sources(paths)
    loaded: dict[Path, SourceFile | None] = {}

    def load(path: Path) -> SourceFile | None:
        if path in sources:
            return sources[path][1]
        if path not in loaded:
            loaded[path] = _outside(path)
        return loaded[path]

    def read(path: Path) -> str:
        found = load(path)
        if found is None:
            raise OSError(path)
        return found.text

    found: defaultdict[str, list[tuple[int, int, str, str]]] = defaultdict(list)
    root = workspace.resolve()
    server = ServerSession(root, read)
    index = RunIndex(root, load, server, IndexCache(root))
    unique = list(dict.fromkeys(names))
    try:
        index.prepare(set(unique), list(sources))
        index.build()
        probe_round(index, [(resolved, source) for resolved, (_, source) in sources.items()], unique, load)
        for name in unique:
            scan = MemberScan(index, name, load)
            for resolved, (shown, source) in sources.items():
                found[shown] += [(b.line, b.col, name, blindspot_text(shown, b, name))
                                 for b in scan.blindspots(resolved, source) if b.check in checks]
    finally:
        server.close()
        index.close()
    return {shown: [(line, text) for line, _, _, text in sorted(spots)] for shown, spots in found.items()}


def _findings(path: Path, selected: set[str], spots: list[tuple[int, str]]) -> list[str]:
    """The file's findings, its blind `spots` last among them, in line order; ties keep check order."""
    source = path.read_text()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [message("compliance.parse-error", path=str(path), line=exc.lineno or 0, error=exc.msg)]
    out: list[tuple[int, str]] = []
    if "untyped-def" in selected:
        out += _check_untyped_defs(tree, path)
    if "unannotated-attr" in selected:
        out += _check_unannotated_attrs(tree, path)
    if "explicit-any" in selected:
        out += check_explicit_any(path, source)
    if "mock" in selected:
        out += mock_findings(path)
    if "rope-walk" in selected and (line := walk_gap_line(source)) is not None:
        out.append((line, message("compliance.rope-walk", path=str(path), line=line)))
    return [text for _, text in sorted([*out, *spots], key=lambda found: found[0])]


def check_path(path: Path, selected: set[str], attr: str | None) -> list[str]:
    """The file's findings in line order, with both attribute checks' when `attr` is given."""
    spots = _blindspots([path], [attr], Path.cwd(), set(ATTR_CHECKS)).get(str(path), []) if attr else []
    return _findings(path, selected, spots)


def _check_native(paths: list[str], selected: set[str], attrs: list[str]) -> int:
    spots: dict[str, list[tuple[int, str]]] = {}
    if attrs:
        try:
            spots = _blindspots([Path(f) for f in paths], attrs, Path.cwd(), selected & set(ATTR_CHECKS))
        except LanguageServerError:
            print(message("compliance.pyright-failed", attr=", ".join(dict.fromkeys(attrs))), file=sys.stderr)
            return 2
    problems = [msg for f in paths for msg in _findings(Path(f), selected, spots.pop(str(Path(f)), []))]
    for msg in problems:
        print(msg)
    return 1 if problems else 0


def run_compliance(*, paths: list[str], select: str | None, attrs: list[str]) -> int:
    """`trmv-compliance`: each file with its language's checks, the other language's in its twin."""
    try:
        selected = compliance_selection(select)
        named = [c.strip() for c in (select or "").split(",") if c.strip() in ATTR_CHECKS]
        if named and not attrs:
            raise RoutingError(message("compliance.attr-required", check=named[0]))
        if selected is not None and not named and attrs:
            raise RoutingError(message("compliance.attr-unselected"))
        groups = split("trmv-compliance", paths, Path.cwd())
    except RoutingError as exc:
        print(exc, file=sys.stderr)
        return 2
    options = [*(["--select", select] if select is not None else []), *(a for attr in attrs for a in ("--attr", attr))]
    own = set(ALL_CHECKS) if selected is None else selected & set(ALL_CHECKS)
    return run_split("trmv-compliance", groups, lambda files: [*options, "--", *files], lambda files: _check_native(files, own, attrs))
