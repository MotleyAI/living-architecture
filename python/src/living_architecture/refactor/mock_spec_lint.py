"""`dr-mock-lint`: every unittest.mock double must be bound to a spec.

Every Mock/MagicMock must carry spec=/spec_set=; every patch()/patch.object() must carry autospec=True (or
an explicit new=/new_callable=/spec=). create_autospec() is always allowed.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from living_architecture.contract import manifest, message
from living_architecture.refactor.routing import RoutingError, run_split, split

MOCK_CTORS = {"Mock", "MagicMock", "NonCallableMock", "NonCallableMagicMock", "AsyncMock"}
SPEC_KWARGS = {"spec", "spec_set"}
PATCH_OK_KWARGS = {"autospec", "new", "new_callable", "spec", "spec_set"}
# Positional arg count at/after which `new` is supplied positionally.
PATCH_NEW_POS = {"patch": 2, "object": 3}


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _patch_kind(call: ast.Call) -> str | None:
    f = call.func
    if isinstance(f, ast.Name) and f.id == "patch":
        return "patch"
    if isinstance(f, ast.Attribute):
        if f.attr == "patch":
            return "patch"
        if f.attr in ("object", "multiple") and _name(f.value) == "patch":
            return f.attr
    return None


def _kwargs(call: ast.Call) -> set[str]:
    return {kw.arg for kw in call.keywords if kw.arg}


def check_file(path: Path) -> list[str]:
    out: list[str] = []
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        kind = _patch_kind(node)
        if kind is not None:
            new_pos = kind in PATCH_NEW_POS and len(node.args) >= PATCH_NEW_POS[kind]
            if not (_kwargs(node) & PATCH_OK_KWARGS) and not new_pos:
                shown = "patch" if kind == "patch" else f"patch.{kind}"
                out.append(message("mock-lint.patch", path=str(path), line=node.lineno, call=shown))
            continue
        name = _name(node.func)
        if name in MOCK_CTORS and not (_kwargs(node) & SPEC_KWARGS):
            out.append(message("mock-lint.mock", path=str(path), line=node.lineno, call=name))
    return out


def _lint_native(paths: list[str]) -> int:
    problems = [msg for f in paths for msg in check_file(Path(f))]
    for msg in problems:
        print(msg)
    return 1 if problems else 0


def run_mock_lint(argv: list[str]) -> int:
    """Handler for raw argv: paths to files or directories, each file linted in its language's twin."""
    if not argv:
        print(f"usage: {manifest()['dr-mock-lint']['usage']}", file=sys.stderr)
        return 2
    try:
        groups = split("dr-mock-lint", argv, Path.cwd())
    except RoutingError as exc:
        print(exc, file=sys.stderr)
        return 2
    return run_split("dr-mock-lint", groups, list, _lint_native)
