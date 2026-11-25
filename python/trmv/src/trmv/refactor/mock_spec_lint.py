"""`trmv-mock-lint`: every unittest.mock double must be bound to a spec.

Every Mock/MagicMock must carry spec=/spec_set=; every patch()/patch.object() must carry autospec=True (or
an explicit new=/new_callable=/spec=). create_autospec() is always allowed.
"""

from __future__ import annotations

import ast
import os
import sys
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from trmv import changes, twin
from trmv.config import ConfigError, find_repo_root
from trmv.contract import message
from trmv.refactor.routing import RoutingError, run_split, split

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


class Double(BaseModel):
    """An unspecced double: its line, finding template and the template's parameters other than path and line."""

    model_config = ConfigDict(frozen=True)

    line: int
    template: str
    call: str

    def text(self, shown: str) -> str:
        return message(self.template, path=shown, line=self.line, call=self.call)


def _call_double(node: ast.Call) -> Double | None:
    """The double `node` builds or patches without a spec, if it is one."""
    kind = _patch_kind(node)
    if kind is not None:
        new_pos = kind in PATCH_NEW_POS and len(node.args) >= PATCH_NEW_POS[kind]
        if _kwargs(node) & PATCH_OK_KWARGS or new_pos:
            return None
        return Double(line=node.lineno, template="mock-lint.patch", call="patch" if kind == "patch" else f"patch.{kind}")
    name = _name(node.func)
    if name in MOCK_CTORS and not (_kwargs(node) & SPEC_KWARGS):
        return Double(line=node.lineno, template="mock-lint.mock", call=name)
    return None


def doubles(text: str, path: Path) -> list[Double]:
    """Each unspecced double of the source `text`."""
    calls = (node for node in ast.walk(ast.parse(text, filename=str(path))) if isinstance(node, ast.Call))
    return [found for node in calls if (found := _call_double(node)) is not None]


def mock_findings(path: Path) -> list[tuple[int, str]]:
    """Each unspecced double's line and finding."""
    return [(d.line, d.text(str(path))) for d in doubles(path.read_text(encoding="utf-8"), path)]


def check_file(path: Path) -> list[str]:
    return [text for _, text in mock_findings(path)]


class Base(BaseModel):
    """The merge base a `--base` run compares with, and the paths renamed since."""

    model_config = ConfigDict(frozen=True)

    repo_root: Path
    commit: str
    renamed: dict[str, str]

    def doubles(self, path: Path) -> list[Double]:
        """`path`'s doubles at the base, read through its path there."""
        rel = Path(os.path.relpath(path.resolve(), self.repo_root)).as_posix()
        data = changes.file_at(ref=self.commit, path=self.renamed.get(rel, rel), repo_root=self.repo_root)
        if data is None:
            return []
        try:
            return doubles(data.decode("utf-8"), path)
        except (SyntaxError, ValueError):
            return []


def _new(current: list[Double], base: list[Double]) -> list[Double]:
    """The doubles of `current` beyond the base's count of their kind, the earliest lines taken as the base's."""
    left = Counter((d.template, d.call) for d in base)
    kept: set[int] = set()
    for i, d in sorted(enumerate(current), key=lambda item: item[1].line):
        if left[(d.template, d.call)] > 0:
            left[(d.template, d.call)] -= 1
        else:
            kept.add(i)
    return [d for i, d in enumerate(current) if i in kept]


def _lint_native(paths: list[str], base: Base | None) -> int:
    problems: list[str] = []
    for f in paths:
        path = Path(f)
        found = doubles(path.read_text(encoding="utf-8"), path)
        if base is not None and found:
            found = _new(found, base.doubles(path))
        problems += [d.text(f) for d in found]
    for msg in problems:
        print(msg)
    return 1 if problems else 0


def _base(branch: str) -> Base:
    repo_root = find_repo_root(Path.cwd())
    ref = changes.resolve_base_ref(base=branch, repo_root=repo_root)
    commit = changes.merge_base(base_ref=ref, repo_root=repo_root)
    return Base(repo_root=repo_root, commit=commit, renamed=changes.base_paths(ref=commit, repo_root=repo_root))


def run_mock_lint(*, paths: list[str], base: str | None) -> int:
    """`trmv-mock-lint`: each file linted in its language's twin; with `base`, only the findings the base lacks."""
    try:
        groups = split("trmv-mock-lint", paths, Path.cwd())
        compared = _base(base) if base is not None and twin.NATIVE_LANGUAGE in groups else None
    except (RoutingError, ConfigError) as exc:
        print(exc, file=sys.stderr)
        return 2
    options = ["--base", base] if base is not None else []
    return run_split("trmv-mock-lint", groups, lambda files: [*options, "--", *files], lambda files: _lint_native(files, compared))
