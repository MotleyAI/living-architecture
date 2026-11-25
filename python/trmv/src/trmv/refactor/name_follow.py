"""A rename's view of the names that hold a string: the project literals a read holds, the member forms naming the
old name through such a name, and the reads of a rewritten literal."""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from trmv.refactor.entry_location import EntryLocator
from trmv.refactor.literal_sources import Follower, Source
from trmv.refactor.member_scan import FORMS, REGISTRY, FormCall, MemberScan, named_uses
from trmv.refactor.python_project import Snapshot
from trmv.refactor.python_source import SourceFile

_DISPLAYS = (ast.Tuple, ast.List, ast.Set)


class Held(BaseModel):
    """A source literal of a project file: its file, the span of its value and its line."""

    model_config = ConfigDict(frozen=True)

    rel: str
    start: int
    end: int
    line: int


class Read(BaseModel):
    """A read of a name holding a source literal: its file, span and the name as written."""

    model_config = ConfigDict(frozen=True)

    rel: str
    start: int
    end: int
    name: str
    held: Held


class NameFollow:
    """Follows the names of the project's Python files (`files`) to their literal sources."""

    def __init__(self, root: Path, snapshot: Snapshot, locator: EntryLocator, files: Callable[[], list[str]]) -> None:
        self.root = root
        self.snapshot = snapshot
        self.locator = locator
        self.files = files
        self.follower = Follower(locator.resolver)
        self._tails = {f.syntax.rsplit(".", 1)[-1] for f in FORMS if f.member is not None} | {r.attribute for r in REGISTRY.name_reads}

    def _held(self, found: list[Source], value: str | None) -> list[Held]:
        files = set(self.files())
        out: list[Held] = []
        for s in found:
            rel = s.path.relative_to(self.root).as_posix() if s.path.is_relative_to(self.root) else None
            if rel is None or rel not in files or (value is not None and s.value != value):
                continue
            start = self.snapshot.source(rel).line_start(s.line) + s.col + 1
            out.append(Held(rel=rel, start=start, end=start + len(s.value), line=s.line))
        return out

    def sources(self, rel: str, expr: ast.expr, value: str | None = None, *, elements: bool = False) -> list[Held]:
        """The project literals (those equal to `value`, when given) the name `expr` of `rel` holds; with `elements`,
        also those of the display it holds."""
        module = self.locator.module(rel)
        scope = self.locator.load_scopes(rel, module).get(id(expr)) if module is not None else None
        if module is None or scope is None:
            return []
        found = self.follower.sources(module, scope, expr)
        if elements and not found:
            found = self.follower.elements(module, scope, expr)
        return self._held(found, value)

    def uses(self, scan: MemberScan) -> dict[str, list[tuple[FormCall, list[Held]]]]:
        """Per file, each resolved member form whose member is a name holding the scan's name, with those literals."""
        out: dict[str, list[tuple[FormCall, list[Held]]]] = {}
        for rel in self.files():
            if not any(tail in self.snapshot.text(rel) for tail in self._tails):
                continue
            source = self.snapshot.source(rel)
            for use in named_uses(source):
                held = self.sources(rel, use.member, scan.name)
                call = scan.named(self.root / rel, source, use) if held else None
                if call is not None:
                    out.setdefault(rel, []).append((call, held))
        return out

    def reads(self, rewritten: set[Held]) -> list[Read]:
        """Every read of a name holding one of `rewritten` that no assignment or loop carries on, by path and offset."""
        out: list[Read] = []
        for rel in self.files():
            module = self.locator.module(rel)
            if module is None:
                continue
            source = self.snapshot.source(rel)
            carried = self.follower.carried(module)
            for expr, _ in module.binder.loads:
                if id(expr) in carried:
                    continue
                held = sorted(set(self.sources(rel, expr, elements=True)) & rewritten, key=lambda h: (h.rel, h.start))
                if held:
                    start, end = source.span(expr)
                    out.append(Read(rel=rel, start=start, end=end, name=source.text[start:end], held=held[0]))
        return sorted(out, key=lambda r: (r.rel, r.start))


def display_names(source: SourceFile, held: Held) -> tuple[str, ...]:
    """The other string elements of the display holding the literal `held` as an element."""
    for node in source.nodes:
        if isinstance(node, _DISPLAYS):
            own = next((e for e in node.elts if isinstance(e, ast.Constant) and source.span(e)[0] == held.start - 1), None)
            if own is not None:
                return tuple(e.value for e in node.elts if e is not own and isinstance(e, ast.Constant) and isinstance(e.value, str))
    return ()
