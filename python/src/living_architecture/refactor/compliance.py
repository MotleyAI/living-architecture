"""`dr-compliance`: report constructs that make a rename un-verifiable.

A rename's completeness can only be proven by a type checker over code the checker can resolve. This flags
the blind spots: untyped-def, unannotated-attr, mock (a double not bound to a spec), and rope-walk (a file rope's
walker cannot cover). With an attribute name it also reports `x.NAME` accesses whose receiver basedpyright types as
`Unknown` or `Any`.
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import TypeGuard

from living_architecture.contract import language, message
from living_architecture.lang import LanguageServer, LanguageServerError
from living_architecture.refactor.mock_spec_lint import check_file as _mock_check
from living_architecture.refactor.python_source import SourceFile
from living_architecture.refactor.rope_patches import apply_rope_patches, walk_gap_line
from living_architecture.refactor.routing import RoutingError, compliance_selection, run_split, split

apply_rope_patches()

ALL_CHECKS = tuple(language("python")["compliance_checks"])
FuncDef = (ast.FunctionDef, ast.AsyncFunctionDef)
_HOVER = re.compile(r"\([\w ]+\) [\w.]+: (.*)", re.DOTALL)


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


def _check_unannotated_attrs(tree: ast.AST, path: Path) -> list[str]:
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        annotated, assigned = _self_attrs(node)
        annotated |= {s.target.id for s in node.body if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)}
        out += [
            message("compliance.unannotated-attr", path=str(path), line=lineno, cls=node.name, attr=name)
            for name, lineno in assigned.items()
            if name not in annotated
        ]
    return out


def _hover_type(hover: str | None) -> str | None:
    """`Unknown` or `Any` when a hover's declared type is, or is a union holding, either; else None."""
    if hover is None or (m := _HOVER.match(hover.split("\n\n")[0])) is None:
        return None
    members: list[str] = []
    depth, start, text = 0, 0, m.group(1)
    for i, char in enumerate(text):
        if char in "[(":
            depth += 1
        elif char in "])":
            depth -= 1
        elif depth == 0 and text.startswith(" | ", i):
            members.append(text[start:i])
            start = i + 3
    members = [t.strip() for t in [*members, text[start:]]]
    return next((kind for kind in ("Unknown", "Any") if kind in members), None)


def _receiver_kind(server: LanguageServer, path: Path, source: SourceFile, node: ast.Attribute) -> str | None:
    """`Unknown` or `Any` in the type of `node`'s receiver: hovered when a name or attribute, else read from the access
    when no declaration of the member is itself typed so."""
    receiver = node.value
    if isinstance(receiver, (ast.Name, ast.Attribute)):
        span = source.name_span(receiver)
        return _hover_type(server.hover(path, span[0])) if span else None
    span = source.name_span(node)
    if span is None or (kind := _hover_type(server.hover(path, span[0]))) is None:
        return None
    declared = (_hover_type(server.hover(d.path, d.start)) for d in server.definition(path, span[0]))
    return None if any(declared) else kind


def _read_sources(paths: list[Path]) -> dict[Path, tuple[str, SourceFile]]:
    """Each distinct file once, keyed by its resolved path, with the path as given."""
    sources: dict[Path, tuple[str, SourceFile]] = {}
    for path in paths:
        resolved = path.resolve()
        if resolved not in sources:
            with open(resolved, encoding="utf-8", newline="") as fh:
                sources[resolved] = (str(path), SourceFile(resolved, fh.read()))
    return sources


def _file_blindspots(
    server: LanguageServer, resolved: Path, shown: str, source: SourceFile, name: str
) -> Iterator[tuple[str, int, int, str]]:
    if source.tree is None:
        return
    for node in ast.walk(source.tree):
        if not (isinstance(node, ast.Attribute) and node.attr == name):
            continue
        if (kind := _receiver_kind(server, resolved, source, node)) is not None:
            receiver = re.sub(r"\s+", " ", source.segment(node.value))
            yield shown, node.lineno, node.col_offset, message(
                "compliance.attr-blindspot", path=shown, line=node.lineno, receiver=receiver, attr=name, type=kind
            )


def attr_blindspots(paths: list[Path], name: str, workspace: Path) -> list[str]:
    """`x.NAME` accesses whose receiver basedpyright types as Unknown or Any, by path, line and column."""
    sources = _read_sources(paths)
    found: list[tuple[str, int, int, str]] = []
    with LanguageServer(workspace) as server:
        for resolved, (_, source) in sources.items():
            server.open(resolved, source.text)
        for resolved, (shown, source) in sources.items():
            found += _file_blindspots(server, resolved, shown, source, name)
    return [text for *_, text in sorted(found)]


def check_path(path: Path, selected: set[str], attr: str | None) -> list[str]:
    source = path.read_text()
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        return [message("compliance.parse-error", path=str(path), line=exc.lineno or 0, error=exc.msg)]
    out: list[str] = []
    if "untyped-def" in selected:
        out += _check_untyped_defs(tree, path)
    if "unannotated-attr" in selected:
        out += _check_unannotated_attrs(tree, path)
    if "mock" in selected:
        out += _mock_check(path)
    if "rope-walk" in selected and (line := walk_gap_line(source)) is not None:
        out.append(message("compliance.rope-walk", path=str(path), line=line))
    if attr:
        out += attr_blindspots([path], attr, Path.cwd())
    return sorted(out)


def _check_native(paths: list[str], selected: set[str], attr: str | None) -> int:
    problems = [msg for f in paths for msg in check_path(Path(f), selected, None)]
    if attr:
        try:
            problems += attr_blindspots([Path(f) for f in paths], attr, Path.cwd())
        except LanguageServerError:
            print(message("compliance.pyright-failed", attr=attr), file=sys.stderr)
            return 2
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
