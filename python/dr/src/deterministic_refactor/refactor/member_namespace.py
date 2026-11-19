"""A member rename's class namespace: the members of the new name its class, every ancestor (library classes and the
implicit root included) and every project descendant declare, by the checker's class facts."""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from deterministic_refactor.contract import language
from deterministic_refactor.lang import PositionFacts
from deterministic_refactor.refactor.bindings import Conflict, Site, may_name
from deterministic_refactor.refactor.members import member_declarations
from deterministic_refactor.refactor.python_source import SourceFile, nfkc

# A project class: its file and the line of its `class` statement.
ClassKey = tuple[str, int]


class ClassFacts(Protocol):
    def class_facts(self, path: Path, offset: int) -> PositionFacts: ...


class RenamedMember(BaseModel):
    """A member declaration a map entry renames: the entry, its new name, the declaration's site and its class."""

    model_config = ConfigDict(frozen=True)

    entry: int
    new_name: str
    site: Site
    cls: ClassKey


class Hierarchy:
    """Project classes and their ancestors, as the checker resolves them."""

    def __init__(self, root: Path, files: list[str], source: Callable[[str], SourceFile], facts: ClassFacts) -> None:
        self.root = root
        self.files = set(files)
        self.source = source
        self.facts = facts
        self.root_members = frozenset(language("python")["root_members"])
        self._facts: dict[ClassKey, PositionFacts | None] = {}

    def node(self, key: ClassKey) -> ast.ClassDef | None:
        return next((c for c in self.source(key[0]).of_type(ast.ClassDef) if c.lineno == key[1]), None)

    def _class_facts(self, key: ClassKey) -> PositionFacts | None:
        if key not in self._facts:
            node = self.node(key)
            span = self.source(key[0]).name_span(node) if node is not None else None
            self._facts[key] = self.facts.class_facts(self.root / key[0], span[0]) if span is not None else None
        return self._facts[key]

    def _key(self, path: Path, start: int) -> ClassKey | None:
        """The project class whose name starts at `start` of the file at `path`."""
        rel = path.relative_to(self.root).as_posix() if path.is_relative_to(self.root) else None
        if rel is None or rel not in self.files:
            return None
        source = self.source(rel)
        return next(((rel, c.lineno) for c in source.of_type(ast.ClassDef)
                     if (span := source.name_span(c)) is not None and span[0] == start), None)

    def ancestors(self, key: ClassKey) -> list[ClassKey]:
        """Every project ancestor of a project class, in MRO order."""
        facts = self._class_facts(key)
        found = (self._key(s.path, s.start) for s in facts.ancestors) if facts is not None else ()
        return [k for k in found if k is not None and k != key]

    def library_members(self, key: ClassKey) -> frozenset[str]:
        """The run's new member names a library ancestor of the class declares."""
        facts = self._class_facts(key)
        return frozenset(facts.members) if facts is not None else frozenset()

    def declarations(self, key: ClassKey, name: str) -> list[Site]:
        """The sites of member `name` a project class declares."""
        node = self.node(key)
        source = self.source(key[0])
        spans = (source.name_span(n) for n in (member_declarations(node, name) if node is not None else []))
        return [(key[0], span[0]) for span in spans if span is not None]


class MemberCheck:
    """Refuses a member renamed onto a name its class's namespace already holds."""

    def __init__(self, hierarchy: Hierarchy, text: Callable[[str], str]) -> None:
        self.hierarchy = hierarchy
        self.text = text
        self._declaring: dict[str, list[ClassKey]] = {}

    def _declaring_classes(self, name: str) -> list[ClassKey]:
        """The project classes declaring member `name`, the project scanned once per name."""
        if name not in self._declaring:
            word = re.compile(rf"(?<!\w){re.escape(name)}(?!\w)")
            self._declaring[name] = [
                (rel, cls.lineno)
                for rel in sorted(self.hierarchy.files) if may_name(word, self.text(rel))
                for cls in self.hierarchy.source(rel).of_type(ast.ClassDef) if member_declarations(cls, name)
            ]
        return self._declaring[name]

    def _descendants(self, key: ClassKey, name: str) -> list[ClassKey]:
        """The project classes declaring member `name` that have `key` among their ancestors."""
        return [other for other in self._declaring_classes(name)
                if other != key and key in self.hierarchy.ancestors(other)]

    def conflicts(self, renamed: list[RenamedMember], renamed_sites: set[Site]) -> list[Conflict]:
        """The sites refusing each renamed member; `renamed_sites` are every declaration the renames rename."""
        out: list[Conflict] = []
        own: defaultdict[int, set[Site]] = defaultdict(set)
        for m in renamed:
            own[m.entry].add(m.site)
        for member in renamed:
            name = member.new_name
            spelled = nfkc(name)
            family = [member.cls, *self.hierarchy.ancestors(member.cls), *self._descendants(member.cls, spelled)]
            existing = [s for key in family for s in self.hierarchy.declarations(key, spelled) if s not in renamed_sites]
            out += [Conflict(site=s, name=name, entry=member.entry) for s in existing]
            met = [m for m in renamed if m.entry != member.entry and m.site not in own[member.entry]
                   and nfkc(m.new_name) == spelled and m.cls in family]
            if met:
                meeting = sorted([member, *met], key=lambda m: (m.entry, m.site))
                first = min(m.site for m in renamed if m.entry == meeting[0].entry)
                out.append(Conflict(site=first, name=meeting[-1].new_name, entry=meeting[-1].entry))
            if spelled in self.hierarchy.root_members or spelled in self.hierarchy.library_members(member.cls):
                out.append(Conflict(site=member.site, name=name, entry=member.entry))
        return out
