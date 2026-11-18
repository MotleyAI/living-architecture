"""The text sites of one old name decided once over the renames sharing it: declared string-form sites, and with
`--docs` every mention, each rewritten for exactly one rename or listed."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator

from pydantic import BaseModel, ConfigDict

from deterministic_refactor.refactor.hierarchy import ClassGraph, GraphClass
from deterministic_refactor.refactor.members import member_declarations
from deterministic_refactor.refactor.mentions import Mention, code_marked
from deterministic_refactor.refactor.outcomes import mention_outcome
from deterministic_refactor.refactor.python_source import SourceFile
from deterministic_refactor.refactor.rename_union import Session, SymbolRename, top_declarations

Site = tuple[str, int]


class Listed(BaseModel):
    """A listed mention: its file, line and span."""

    model_config = ConfigDict(frozen=True)

    rel: str
    line: int
    start: int
    end: int


def _class_spans(source: SourceFile) -> list[tuple[int, int, ast.ClassDef]]:
    """Each class's span, from its first decorator to the end of its last line."""
    out: list[tuple[int, int, ast.ClassDef]] = []
    text = source.text
    for cls in source.of_type(ast.ClassDef):
        start, end = source.span(cls)
        if cls.decorator_list:
            start = text.rfind("@", 0, min(source.span(d)[0] for d in cls.decorator_list))
        line_end = text.find("\n", end)
        out.append((start, len(text) if line_end < 0 else line_end, cls))
    return out


def _form_sites(text: str, start: int, end: int, old: str, forms: list[re.Pattern[str]]) -> Iterator[tuple[int, int]]:
    """The spans of `old` as the symbol group of a form matching in the literal part `start:end`."""
    part = text[start:end]
    if old not in part or not part.isascii():
        return
    for form in forms:
        for match in form.finditer(part):
            if match.group(1) == old:
                yield start + match.start(1), start + match.end(1)


class GroupMentions:
    """The renames of one old name (`renames`, in entry order) and the decisions they share."""

    def __init__(self, session: Session, graph: ClassGraph, renames: list[SymbolRename], forms: list[re.Pattern[str]]) -> None:
        self.session = session
        self.graph = graph
        self.renames = renames
        self.forms = forms
        self.old = renames[0].old
        self.listed: list[Listed] = []
        self._rules = [r.mention_rules() for r in renames]
        self._handled: dict[str, list[tuple[int, int]]] = {}
        self._spans: dict[str, list[tuple[int, int, ast.ClassDef]]] = {}
        self._file_names: dict[str, str | None] = {}

    def _new_names(self, sites: set[Site]) -> str | None:
        """The one new name the renames give every one of `sites`, else None."""
        names: set[str] = set()
        for site in sites:
            found = {r.new for r in self.renames if r.renames_site(site)}
            if not found:
                return None
            names |= found
        return next(iter(names)) if len(names) == 1 else None

    def _owner(self, new: str) -> SymbolRename:
        return next(r for r in self.renames if r.new == new)

    def _files(self) -> list[str]:
        return sorted({rel for r in self.renames for rel in r.candidates})

    # ---- string forms

    def form_sites(self) -> None:
        """Each form site of a class or module-level rename: rewritten when every module-level declaration of the
        name in the project is renamed to one name, else listed."""
        if not self.forms or not any(r.entry.kind == "name" for r in self.renames):
            return
        files = self._files()
        declared = {site for rel in files for site in self._top_sites(rel)}
        new = self._new_names(declared) if declared else None
        for rel in files:
            source = self.session.snapshot.source(rel)
            sites = {
                site
                for start, end, where in self.session.tables.regions(rel) if where != "comment"
                for site in _form_sites(source.text, start, end, self.old, self.forms)
            }
            for start, end in sorted(sites):
                if any(r.handled(rel, start, end) for r in self.renames):
                    continue
                self._handled.setdefault(rel, []).append((start, end))
                self._decide(rel, Mention(start=start, end=end, line=source.line(start), where="string"), new)

    def _top_sites(self, rel: str) -> Iterator[Site]:
        """The module-level declarations of the old name in `rel`."""
        source = self.session.snapshot.source(rel)
        for stmt in source.tree.body if source.tree else []:
            for node in top_declarations(stmt, self.old):
                span = source.name_span(node)
                if span is not None:
                    yield rel, span[0]

    # ---- mentions

    def mentions(self) -> None:
        """Every `--docs` mention of the old name no other rule handled."""
        declaring = {rel for r in self.renames for rel, _ in r.seeds}
        first = self.renames[0]
        files = [(rel, first.source_mentions(rel)) for rel in self._files()]
        files += [(rel, found) for rel in self.session.tables.prose() if (found := first.prose_mentions(rel)) is not None]
        for rel, found in files:
            text = self.session.snapshot.text(rel)
            for m in sorted(found, key=lambda m: m.start):
                if self._is_handled(rel, m):
                    continue
                self._decide(rel, m, self._new_name(rel, text, m, rel in declaring))

    def _is_handled(self, rel: str, m: Mention) -> bool:
        if any(s < m.end and m.start < e for s, e in self._handled.get(rel, ())):
            return True
        return any(r.handled(rel, m.start, m.end) for r in self.renames)

    def _decide(self, rel: str, m: Mention, new: str | None) -> None:
        owner = self.renames[0] if new is None else self._owner(new)
        owner.file(mention_outcome(rel, m, rewrite=new is not None, old=self.old, new=new or ""))
        if new is None:
            self.listed.append(Listed(rel=rel, line=m.line, start=m.start, end=m.end))

    def _new_name(self, rel: str, text: str, m: Mention, declaring: bool) -> str | None:
        """The new name a mention takes: a qualified one its owner's, a code-marked one of a declaring file its owning
        class's or its file's; None when it is listed."""
        qualified = {r.new for r, rules in zip(self.renames, self._rules, strict=True) if rules.qualified(text, m.start)}
        if qualified:
            return next(iter(qualified)) if len(qualified) == 1 else None
        if not declaring or not code_marked(text, m):
            return None
        carves = self.renames[0].carves
        if carves is not None and carves.covers(rel, self.old, m.start):
            return None
        source = self.session.snapshot.source(rel)
        if rel not in self._spans:
            self._spans[rel] = _class_spans(source)
        enclosing = sorted((s for s in self._spans[rel] if s[0] <= m.start < s[1]), key=lambda s: s[1] - s[0])
        for _, _, cls in enclosing:
            found = self.graph.lookup(self.graph.of(source, cls), self.old)
            if isinstance(found, GraphClass):
                return self._new_names(self._member_sites(found))
            if found:
                return None
        if rel not in self._file_names:
            self._file_names[rel] = self._file_name(rel, source)
        return self._file_names[rel]

    def _member_sites(self, cls: GraphClass) -> set[Site]:
        rel = self.session.rel(cls.source.path)
        spans = (cls.source.name_span(n) for n in member_declarations(cls.node, self.old))
        return {(rel or "", span[0] if span else -1) for span in spans}

    def _file_name(self, rel: str, source: SourceFile) -> str | None:
        """The one name every module-level and class-member declaration of the old name in `rel` is renamed to; with
        no such declaration, the one name of the renames declaring in it."""
        assert source.tree is not None
        nodes = [n for stmt in source.tree.body for n in top_declarations(stmt, self.old)]
        nodes += [n for cls in source.of_type(ast.ClassDef) for n in member_declarations(cls, self.old)]
        sites = {(rel, span[0] if span else -1) for span in map(source.name_span, nodes)}
        if sites:
            return self._new_names(sites)
        names = {r.new for r in self.renames if any(path == rel for path, _ in r.seeds)}
        return next(iter(names)) if len(names) == 1 else None
