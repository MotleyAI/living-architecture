"""A Python symbol rename: every occurrence the run's occurrence index resolves to a renamed declaration (and those
la's static resolver resolves to one where the checker resolves none), the keyed-class rewrites, member strings and
patch targets, and with `--docs` mentions, as character spans over one snapshot of the project's files; a member
rename first checks for blind spots and stand-ins."""

from __future__ import annotations

import ast
import bisect
import keyword
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from functools import partial
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ConfigDict
from typing_extensions import override

from living_architecture.contract import message
from living_architecture.lang import Occurrence, Span
from living_architecture.refactor.carve_outs import CarveOuts, is_fixture
from living_architecture.refactor.entry_location import Entry, EntryLocator, StaticTrace
from living_architecture.refactor.hierarchy import ClassGraph, ClassKey
from living_architecture.refactor.keyed import (
    Bindings,
    ClassRef,
    KeyedRename,
    TypeFacts,
    declares_alias,
    field_assignment,
    sink_candidates,
)
from living_architecture.refactor.locators import cannot_rename
from living_architecture.refactor.member_scan import FormCall, MemberScan
from living_architecture.refactor.members import member_declarations
from living_architecture.refactor.mentions import (
    Mention,
    MentionRules,
    Owner,
    classify,
    mentions,
)
from living_architecture.refactor.move_edits import NameConflict
from living_architecture.refactor.occurrence_index import RunIndex
from living_architecture.refactor.outcomes import (
    Finding,
    Outcome,
    blindspot_outcome,
    compound_outcome,
    file_outcome,
    literal_outcomes,
    mention_outcome,
    string_member_outcome,
    target_outcome,
)
from living_architecture.refactor.patch_targets import SourceFolders, TargetResolver
from living_architecture.refactor.python_project import ProjectLayout, Snapshot
from living_architecture.refactor.python_source import SourceFile, every_parameter, nfkc
from living_architecture.refactor.routing import language_files
from living_architecture.refactor.sites import Site
from living_architecture.refactor.static_resolver import Module
from living_architecture.refactor.text_edits import TextEdit
from living_architecture.refactor.text_tables import TextTables
from living_architecture.refactor.timings import timed

_T = TypeVar("_T")


class Session:
    """One refactor's view of the project at `root`: its layout, the snapshot, and files read outside it."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.layout = ProjectLayout(self.root)
        self.snapshot = Snapshot(self.root)
        self._tables: TextTables | None = None
        self._loaded: dict[Path, SourceFile | None] = {}
        self._all_python_files: list[str] | None = None
        self._python_files: list[str] | None = None

    @property
    def tables(self) -> TextTables:
        if self._tables is None:
            self._tables = TextTables(self.root, self.snapshot.source)
        return self._tables

    def drop_parsed(self) -> None:
        """Forget the text tables, the files read from outside the project and the snapshot's parsed files."""
        self._tables = None
        self._loaded.clear()
        self.snapshot.drop_parsed()

    def rel(self, path: Path) -> str | None:
        return path.relative_to(self.root).as_posix() if path.is_relative_to(self.root) else None

    def modname(self, rel: str) -> str:
        return self.layout.modname(self.root / rel)

    def source_folders(self) -> list[str]:
        """The project's source folders as relative paths, the root (`""`) among them."""
        return sorted({"", *self.layout.source_rels})

    def all_python_files(self) -> list[str]:
        """The project's Python files, by path, as they were before the run."""
        if self._all_python_files is None:
            self._all_python_files = [p.relative_to(self.root).as_posix() for p in language_files(self.root, "python")]
        return self._all_python_files

    def python_files(self) -> list[str]:
        """The project's Python files that decode, by path."""
        if self._python_files is None:
            self._python_files = [rel for rel in self.all_python_files() if self.snapshot.undecodable(rel) is None]
        return self._python_files

    def load(self, path: Path) -> SourceFile | None:
        if path not in self._loaded:
            self._loaded[path] = self._read(path)
        return self._loaded[path]

    def _read(self, path: Path) -> SourceFile | None:
        if path.is_relative_to(self.root) and path.suffix in (".py", ".pyi") and path.is_file():
            return self.snapshot.source(path.relative_to(self.root).as_posix())
        try:
            with open(path, encoding="utf-8", newline="") as fh:
                return SourceFile(path, fh.read())
        except (OSError, UnicodeDecodeError):
            return None

    def read(self, path: Path) -> str:
        source = self.load(path)
        if source is None:
            raise OSError(path)
        return source.text


def _declarations(source: SourceFile) -> set[tuple[int, int]]:
    """The spans of every name `source` declares: defs, classes, parameters and assignment targets."""
    if source.tree is None:
        return set()
    out: set[tuple[int, int]] = set()
    for node in source.nodes:
        stored = isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Store)
        if stored or isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.arg)):
            span = source.name_span(node)
            if span is not None:
                out.add(span)
    return out


def _field_of(source: SourceFile, line: int, name: str) -> tuple[ClassRef, ast.AnnAssign | ast.Assign, Span] | None:
    """The class whose body declares field `name` at `line`, with the declaration."""
    if source.tree is None:
        return None
    classes = (n for n in source.nodes if isinstance(n, ast.ClassDef))
    for cls in classes:
        for stmt in cls.body:
            found = field_assignment(stmt, name) if stmt.lineno == line else None
            if found is not None:
                start, end = source.span(found[1])
                return ClassRef(source, cls), found[0], Span(path=source.path, start=start, end=end)
    return None


def _named_items(source: SourceFile, node: ast.AST) -> list[tuple[object, int, tuple[int, int] | None]]:
    """A call's keywords or a literal's constant keys: each name, line and span."""
    if isinstance(node, ast.Call):
        return [(k.arg, k.lineno, source.name_span(k)) for k in node.keywords]
    if isinstance(node, (ast.Dict, ast.Set)):
        keys = node.keys if isinstance(node, ast.Dict) else node.elts
        return [(k.value, k.lineno, source.span(k)) for k in keys if isinstance(k, ast.Constant)]
    return []


def _conflict(source: SourceFile, rel: str, edits: list[TextEdit], old: str, new: str) -> None:
    """Raise `NameConflict` where a renamed keyword or key meets the new name in the same call or literal."""
    if source.tree is None:
        return
    starts = sorted(e.start for e in edits)

    def edited(span: tuple[int, int] | None) -> bool:
        if span is None:
            return False
        i = bisect.bisect_left(starts, span[0])
        return i < len(starts) and starts[i] < span[1]

    for node in source.nodes:
        items = _named_items(source, node)
        if any(name == new for name, _, _ in items):
            line = next((line for name, line, span in items if name == old and edited(span)), None)
            if line is not None:
                raise NameConflict(new, rel, line)


Function = ast.FunctionDef | ast.AsyncFunctionDef


def _parameter(fn: Function, name: str) -> ast.arg | None:
    """`fn`'s parameter `name`, of any kind."""
    return next((a for a in every_parameter(fn.args) if a.arg == name), None)


def _same_named(source: SourceFile, fn: Function) -> list[Function]:
    """The defs named like `fn` in the module or class body holding it; `[fn]` in any other body."""
    holder = source.parent(fn)
    if isinstance(holder, (ast.Module, ast.ClassDef)) and any(stmt is fn for stmt in holder.body):
        return [s for s in holder.body if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)) and s.name == fn.name]
    return [fn]


class RenameOptions(BaseModel):
    """How a symbol rename runs: hierarchy, unsure occurrences, the blind-spot override, stand-in classifications,
    kept sites, the mention scan and whether the run stops at its first refusal."""

    model_config = ConfigDict(frozen=True)

    in_hierarchy: bool = True
    unsure: bool = False
    allow_blindspots: bool = False
    with_sites: tuple[str, ...] = ()
    without_sites: tuple[str, ...] = ()
    keep: tuple[str, ...] = ()
    docs: bool = False
    fail_fast: bool = False
    stub: str | None = None
    words: str | None = None


class Declaration(BaseModel):
    """A class member named like the renamed symbol: its file, name span, line and class."""

    model_config = ConfigDict(frozen=True)

    rel: str
    start: int
    line: int
    cls: str


class RenameResult(BaseModel):
    """What a run reads of a map entry's rename once its rules are done: the entry's map index, its target's name for
    a retarget, the edits the keeps dropped (`kept`), and the member declarations it may rename."""

    entry: int
    old: str
    new: str
    header: str
    target: str | None
    member: bool
    check_names: bool
    edits: list[TextEdit]
    kept: list[TextEdit] = []
    imports: list[TextEdit] = []
    blindspots: list[Finding]
    unresolved: list[Finding] = []
    stand_ins: list[Finding] = []
    refusals: list[Finding] = []
    matched_sites: frozenset[str] = frozenset()
    declarations: list[Declaration] = []

    def live(self) -> bool:
        """The rename changes a name."""
        return self.new != self.old

    def renamed_members(self, snapshot: Snapshot) -> list[tuple[tuple[str, int], tuple[str, int]]]:
        """Each member declaration this rename's edits rename, with its class's file and `class` line."""
        if not self.member:
            return []
        starts = {(e.path, e.start) for e in self.edits}
        out: list[tuple[tuple[str, int], tuple[str, int]]] = []
        for d in self.declarations:
            source = snapshot.source(d.rel)
            if (d.rel, d.start) not in starts or source.tree is None:
                continue
            owner = next((cls for cls in source.of_type(ast.ClassDef) if any(
                (span := source.name_span(n)) is not None and span[0] == d.start
                for n in member_declarations(cls, self.old))), None)
            if owner is not None:
                out.append(((d.rel, d.start), (d.rel, owner.lineno)))
        return out

    def check_conflicts(self, snapshot: Snapshot, edits: list[TextEdit]) -> None:
        """`NameConflict` where one of `edits` (this rename's, merged) meets the new name."""
        if not self.check_names:
            return
        for rel in sorted({e.path for e in edits}):
            _conflict(snapshot.source(rel), rel, [e for e in edits if e.path == rel], self.old, self.new)


class MapRename(ABC):
    """A rename map entry's phases, run over all entries in turn: `prepare`, `seed` and `rules` (on the run's
    occurrence index), `finish`; then its `result`."""

    @abstractmethod
    def header(self) -> str: ...

    @abstractmethod
    def stand_in_findings(self) -> list[Finding]: ...

    @abstractmethod
    def prepare(self, index: RunIndex) -> None: ...

    @abstractmethod
    def seed(self, facts: TypeFacts) -> None: ...

    @abstractmethod
    def rules(self, index: RunIndex, facts: TypeFacts) -> None: ...

    @abstractmethod
    def finish(self) -> None: ...

    @abstractmethod
    def result(self, entry: int, target: str | None, kept: list[TextEdit]) -> RenameResult: ...


class SymbolRename(MapRename):
    """A rename of a symbol other than a module, its `entry` located at `site` (a file and an offset in its text) by
    `locator`: `prepare` finds the renamed declarations and the stand-ins, `rules` the edits, `finish` the mentions and
    leftovers."""

    def __init__(self, session: Session, entry: Entry, new_name: str, options: RenameOptions | None = None, *,
                 site: tuple[str, int], locator: EntryLocator, carves: CarveOuts | None = None) -> None:
        self.session = session
        self.carves = carves
        self.site = site
        self.entry = entry
        self.locator = locator
        self._index: RunIndex | None = None
        self._graph: ClassGraph | None = None
        self._located_sites: set[tuple[str, int]] = set()
        self.options = options or RenameOptions()
        self.old: str = entry.name
        self.new = new_name
        self.root = session.root
        self.snapshot = session.snapshot
        self.is_renamed: Callable[[tuple[str, int]], bool] = lambda site: site in self.seeds
        self.matched_sites: set[str] = set()
        self.member = False
        self.check_names = True
        self.renamed_names: set[str] = {self.old}
        self._fields: list[tuple[ClassRef, ast.AnnAssign | ast.Assign, Span]] = []
        self.edits: list[TextEdit] = []
        self.seeds: set[tuple[str, int]] = set()
        self.keywordless: set[tuple[str, int]] = set()
        self.candidates: list[str] = []
        self._files: list[str] = []
        self.entries: list[Entry] = [entry]
        self.blindspots: list[Finding] = []
        self.stand_ins: list[Finding] = []
        self.leftovers: list[Finding] = []
        self.unresolved: list[Finding] = []
        self._declarations: list[Declaration] = []
        self._unclassified: list[Declaration] = []
        self._examined: dict[str, list[tuple[int, int]]] = {}
        self._targets: dict[str, list[tuple[int, int]]] = {}
        self._in_hierarchy = self.options.in_hierarchy
        self._unsure = self.options.unsure

    def _validate(self) -> None:
        if not self.new.isidentifier() or keyword.iskeyword(nfkc(self.new)):
            raise cannot_rename()

    def _project_declarations(self, found: Occurrence | None) -> set[tuple[str, int]]:
        if found is None:
            return set()
        return {(rel, d.span.start) for d in found.declarations if (rel := self.session.rel(d.span.path)) is not None}

    def _located(self, index: RunIndex) -> set[tuple[str, int]]:
        """An import alias's own binding at the entry's site, else the declarations the checker resolves the site to;
        where it resolves none in the project, the declarations on the line of the entry's first."""
        rel, offset = self.site
        at = index.at(self.root / rel, self.old, offset)
        if at is not None and at.kind == "alias":
            return {(rel, at.span.start)}
        found = self._project_declarations(at)
        if found or not self.entry.sites:
            return found
        first, start = self.entry.sites[0]
        source = self.snapshot.source(first)
        line = source.line(start)
        return {(first, s) for s, e in _declarations(source) if source.line(s) == line and source.text[s:e] == self.old}

    def _member_declarations(self, index: RunIndex) -> list[Declaration]:
        """Every declaration of a class member named like the symbol, in the candidate files."""
        out = [d for rel in self.candidates
               for d in index.memo(("member_declarations", rel, self.old), partial(self._declared_members, rel))]
        return sorted(out, key=lambda d: (d.rel, d.start))

    def _declared_members(self, rel: str) -> list[Declaration]:
        source = self.snapshot.source(rel)
        out: list[Declaration] = []
        for cls in source.of_type(ast.ClassDef):
            for node in member_declarations(cls, self.old):
                span = source.name_span(node)
                if span is not None:
                    out.append(Declaration(rel=rel, start=span[0], line=source.line(span[0]), cls=cls.name))
        return out

    @override
    def header(self) -> str:
        return message("refactor.rename-header", old=self.old, new=self.new)

    @override
    def result(self, entry: int, target: str | None, kept: list[TextEdit]) -> RenameResult:
        return RenameResult(
            entry=entry, old=self.old, new=self.new, header=self.header(), target=target,
            member=self.member, check_names=self.check_names, edits=self.edits, kept=kept, blindspots=self.blindspots,
            unresolved=self.unresolved, stand_ins=self.stand_in_findings(), matched_sites=frozenset(self.matched_sites),
            declarations=self._declarations if self.member else [],
        )

    def is_member(self) -> bool:
        """The symbol is declared in a class body (or as a `self.` attribute): a declaration the rename renames is one."""
        if self.entry.kind == "parameter":
            return False
        return any((d.rel, d.start) in self.seeds for d in self._declarations)

    def _class_key(self, d: Declaration) -> ClassKey | None:
        """The class declaring member declaration `d`, by the checker's class graph's key."""
        assert self._graph is not None
        source = self.snapshot.source(d.rel)
        for cls in source.of_type(ast.ClassDef):
            if any((span := source.name_span(n)) is not None and span[0] == d.start for n in member_declarations(cls, self.old)):
                return self._graph.of(source, cls).key
        return None

    def _roots(self, d: Declaration) -> frozenset[ClassKey]:
        assert self._graph is not None
        key = self._class_key(d)
        found = self._graph.at(*key) if key is not None else None
        return self._graph.roots(found, self.old) if found is not None else frozenset()

    def _hierarchy(self, index: RunIndex, sites: set[tuple[str, int]], method: bool) -> set[tuple[str, int]]:
        """The member declarations renamed with the member declared at `sites` when the hierarchy is on: for a
        method, those whose class's roots meet its class's; for any other member, its own declarations."""
        spans = {(d.rel, d.start) for d in self._declarations}
        at = [d for d in self._declarations if (d.rel, d.start) in sites]
        if not method:
            return {s for d in at for s in self._own(index, d)} & spans
        roots = frozenset[ClassKey]().union(*(self._roots(d) for d in at))
        return {(d.rel, d.start) for d in self._declarations if self._roots(d) & roots}

    def located_hierarchy(self) -> set[tuple[str, int]]:
        """The hierarchy of the located declaration, whether or not the rename's hierarchy flag is on."""
        assert self._index is not None
        return self._hierarchy(self._index, self._located_sites, self.entry.kind == "method")

    def _own(self, index: RunIndex, d: Declaration) -> set[tuple[str, int]]:
        """The declarations of the member declared at `d`, as the checker resolves its name there."""
        return self._project_declarations(index.at(self.root / d.rel, self.old, d.start)) | {(d.rel, d.start)}

    def _classify(self, index: RunIndex) -> None:
        """The renamed declarations: the hierarchy (with it on) and every `--with` stand-in's; record the stand-ins left
        unclassified."""
        hierarchy = self._hierarchy(index, self.seeds, self.entry.kind == "method")
        stand_ins = [d for d in self._declarations if (d.rel, d.start) not in hierarchy]
        renamed = set(hierarchy) | self.seeds if self._in_hierarchy else set(self.seeds)
        classified: set[tuple[str, int]] = set()
        for raw in self.options.with_sites:
            classified |= self._classify_site(index, raw, stand_ins, renamed)
        for raw in self.options.without_sites:
            classified |= self._classify_site(index, raw, stand_ins, None)
        for d in (d for d in stand_ins if (d.rel, d.start) not in classified):
            found = self.locator.at(d.rel, d.start)
            theirs = self._hierarchy(index, {(d.rel, d.start)}, found.kind == "method") | {(d.rel, d.start)}
            if all(self._left_by_default(site) for site in theirs):
                classified |= theirs
        self._unclassified = [d for d in stand_ins if (d.rel, d.start) not in classified]
        self.seeds = renamed

    def _classify_site(self, index: RunIndex, raw: str, stand_ins: list[Declaration],
                       renamed: set[tuple[str, int]] | None) -> set[tuple[str, int]]:
        """The declarations the `--with` (`renamed` given, which they join) or `--without` site `raw` classifies."""
        site = Site.parse(raw, self.root, base=self.root)
        matched = [d for d in stand_ins if site.line is not None and site.covers(d.rel, d.line)]
        if matched:
            self.matched_sites.add(raw)
        classified: set[tuple[str, int]] = set()
        for d in matched:
            found = self.locator.at(d.rel, d.start)
            theirs = self._hierarchy(index, {(d.rel, d.start)}, found.kind == "method") | {(d.rel, d.start)}
            classified |= theirs
            if renamed is not None:
                self.entries.append(found)
                renamed |= theirs if self._in_hierarchy else self._own(index, d)
        return classified

    def _left_by_default(self, site: tuple[str, int]) -> bool:
        """The member declaration at `site` is a test fixture, or one a carve-out keeps."""
        rel, start = site
        if is_fixture(self.snapshot.source(rel), start):
            return True
        return self.carves is not None and bool(self.carves.carved(rel, self.old, [start]))

    @override
    def stand_in_findings(self) -> list[Finding]:
        """The unclassified stand-ins no entry of the map renames."""
        return [
            Finding(path=d.rel, line=d.line, col=d.start, text=message(
                "refactor.stand-in", path=d.rel, line=d.line, cls=d.cls, attr=self.old))
            for d in self._unclassified
            if not self.is_renamed((d.rel, d.start))
        ]

    def _index_edits(self, index: RunIndex) -> None:
        """Every occurrence resolving to a renamed declaration or through a renamed import alias (a keyword only through
        one that takes keywords), every access with an untyped receiver under `--unsure include`, and each name, import
        or alias the checker resolves to nothing that Python's scoping resolves to a renamed declaration; one nothing
        resolves is listed."""
        unresolved: list[tuple[str, Occurrence]] = []
        for rel in self.candidates:
            for o in index.occurrences(self.root / rel, self.old):
                if self._renames(o) or (self._unsure and o.kind == "member" and o.receiver is not None):
                    self.edits.append(TextEdit(path=rel, start=o.span.start, end=o.span.end, new_text=self.new))
                elif not o.declarations and o.kind in ("name", "import", "alias"):
                    unresolved.append((rel, o))
        trace = StaticTrace(self.locator)
        for rel, o in unresolved:
            found = trace.at(rel, o.span.start, self.old)
            if found.sites & self.seeds:
                self.edits.append(TextEdit(path=rel, start=o.span.start, end=o.span.end, new_text=self.new))
            elif not found.resolved:
                line = self.snapshot.source(rel).line(o.span.start)
                text = message("refactor.unresolved-name", path=rel, line=line, old=self.old)
                self.unresolved.append(Finding(path=rel, line=line, col=o.span.start, text=text))

    def _renames(self, o: Occurrence) -> bool:
        """`o` resolves to a renamed declaration or through a renamed import alias (a keyword only through one that
        takes keywords)."""
        spans = [*(d.span for d in o.declarations), *o.bindings]
        hits = {(r, s.start) for s in spans if (r := self.session.rel(s.path)) is not None} & self.seeds
        if o.kind == "keyword":
            hits -= self.keywordless
        return bool(hits)

    def _located_field(self, entry: Entry) -> tuple[ClassRef, ast.AnnAssign | ast.Assign, Span] | None:
        """The class field `entry` declares first, when its file is a candidate."""
        if not entry.sites or entry.sites[0][0] not in self.candidates:
            return None
        rel, start = entry.sites[0]
        source = self.snapshot.source(rel)
        return _field_of(source, source.line(start), self.old)

    def _keyed_edits(self, index: RunIndex, facts: TypeFacts, field: tuple[ClassRef, ast.AnnAssign | ast.Assign, Span]) -> None:
        owner, stmt, declared = field
        if facts.chain(owner).kind is None:
            return
        keyed = KeyedRename(facts, self.old, self.new, {(declared.path, declared.start)}, aliased=declares_alias(stmt))
        bindings = Bindings()
        for rel in self.candidates:
            source = self.snapshot.source(rel)
            found = index.memo(("keyed_sinks", rel, self.old), partial(sink_candidates, source, self.old))
            keyed.scan(source, rel, bindings, found)
        self.edits += keyed.edits
        self.edits += bindings.edits()

    def _function_at(self, fn: tuple[str, int]) -> tuple[str, Function] | None:
        """The def whose name starts at `fn`, when its file is a candidate."""
        rel, start = fn
        if rel not in self.candidates:
            return None
        source = self.snapshot.source(rel)
        found = (n for n in source.of_type(ast.FunctionDef) + source.of_type(ast.AsyncFunctionDef)
                 if (span := source.name_span(n)) is not None and span[0] == start)
        return next(((rel, n) for n in found), None)

    def _method_declarations(self, located: tuple[str, Function]) -> list[tuple[str, Function]]:
        """The declarations a rename of the method `located` renames: its own, and with the hierarchy on those of every
        class whose roots for its name meet its class's."""
        assert self._graph is not None
        rel, node = located
        name = node.name
        source = self.snapshot.source(rel)
        owner = next((c for c in source.of_type(ast.ClassDef) if any(s is node for s in c.body)), None)
        if owner is None:
            return [located]
        own = self._graph.of(source, owner)
        roots = self._graph.roots(own, name)
        out: list[tuple[str, Function]] = []
        for candidate in self.candidates:
            found = self.snapshot.source(candidate)
            if found.tree is None or name not in found.text:
                continue
            for c in found.of_type(ast.ClassDef):
                graph_class = self._graph.of(found, c)
                same = graph_class.key == own.key
                if same or (self._in_hierarchy and self._graph.roots(graph_class, name) & roots):
                    out += [(candidate, s) for s in c.body if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)) and s.name == name]
        return out

    def _parameter_declarations(self, facts: TypeFacts, fn: tuple[str, int]) -> list[tuple[str, SourceFile, Function, ast.arg]]:
        """The renamed parameters: those named `old` of the method hierarchy's declarations and their overload groups."""
        located = self._function_at(fn)
        if located is None:
            return []
        defs = [located]
        source = self.snapshot.source(located[0])
        if any(any(s is located[1] for s in c.body) for c in source.of_type(ast.ClassDef)):
            defs += self._method_declarations(located)
        seen: set[tuple[str, int, int]] = set()
        out: list[tuple[str, SourceFile, Function, ast.arg]] = []
        for rel, node in defs:
            source = self.snapshot.source(rel)
            assert source.tree is not None
            group = _same_named(source, node)
            for member in group if any(facts.is_overload(source, m) for m in group) else [node]:
                key = (rel, member.lineno, member.col_offset)
                if key not in seen and (arg := _parameter(member, self.old)) is not None:
                    seen.add(key)
                    out.append((rel, source, member, arg))
        return out

    def _parameter_seeds(self, facts: TypeFacts, fn: tuple[str, int]) -> None:
        """Seed every renamed parameter."""
        for rel, source, node, arg in self._parameter_declarations(facts, fn):
            span = source.name_span(arg)
            if span is not None:
                self.seeds.add((rel, span[0]))
                if not any(arg is a for a in (*node.args.args, *node.args.kwonlyargs)):
                    self.keywordless.add((rel, span[0]))

    def _file(self, outcome: Outcome) -> None:
        """Record an examined site and file what its rule decided."""
        self._examined.setdefault(outcome.rel, []).append(outcome.span)
        file_outcome(outcome, edits=self.edits, blindspots=self.blindspots, leftovers=self.leftovers)

    def _overlaps(self, spans: dict[str, list[tuple[int, int]]], rel: str, start: int, end: int) -> bool:
        """`start:end` of `rel` overlaps one of `spans` or an edit."""
        hit = any(s < end and start < e for s, e in spans.get(rel, ()))
        return hit or any(e.path == rel and e.start < end and start < e.end for e in self.edits)

    def _string_member_edits(self, scan: MemberScan) -> None:
        """Rewrite member strings whose object's lookup lands only on renamed declarations; one landing on renamed
        and unchanged declarations is a blind spot."""
        for rel in self.candidates:
            path, source = self.root / rel, self.snapshot.source(rel)
            calls = [c for c in scan.member_calls(path, source) if c.forms]
            if not calls:
                continue
            for call, (_, definitions) in zip(calls, scan.probe(path, calls), strict=True):
                sites = [(self.session.rel(d.path) or "", d.start) for d in definitions]
                renamed = [self.is_renamed(s) for s in sites] if any(s in self.seeds for s in sites) else []
                self._file(string_member_outcome(rel, source, call, renamed, self.old, self.new))

    def _declared(self, module: Module, node: ast.AST) -> tuple[str, int] | None:
        rel = self.session.rel(module.path) if module.path is not None else None
        span = self.snapshot.source(rel).name_span(node) if rel is not None else None
        return (rel, span[0]) if rel is not None and span is not None else None

    def _target_edits(self, scan: MemberScan, member: bool) -> None:
        """Rewrite dotted target segments that resolve to a renamed declaration; refuse or list the rest."""
        folders = SourceFolders(self.session.layout.source_folders())
        targets = TargetResolver(folders, self.session.read)
        for rel in self.candidates:
            source = self.snapshot.source(rel)
            for call in scan.target_calls(self.root / rel, source):
                self._targets.setdefault(rel, []).append(call.literal)
                self._file(self._target_outcome(rel, source, call, folders, targets, member))

    def _target_outcome(
        self, rel: str, source: SourceFile, call: FormCall, folders: SourceFolders, targets: TargetResolver, member: bool
    ) -> Outcome:
        project_target = folders.top_level(call.text.split(".")[0])
        resolved = targets.resolve(call.text) if project_target and call.forms is not None else None
        renamed = None if resolved is None else [any(self._declared(m, n) in self.seeds for m, n in d) for d in resolved]
        return target_outcome(rel, source, call, project_target=project_target, renamed=renamed, member=member,
                              old=self.old, new=self.new)

    def _blindspot_scan(self, scan: MemberScan) -> None:
        for rel in self.candidates:
            source = self.snapshot.source(rel)
            for b in scan.blindspots(self.root / rel, source):
                self._file(blindspot_outcome(rel, source, b, self.old))

    def _owners(self) -> set[Owner]:
        """The qualifying paths of the renamed module-level and class-member declarations."""
        out: set[Owner] = set()
        for rel, start in self.seeds:
            source = self.snapshot.source(rel)
            if source.tree is None:
                continue
            module = tuple(self.session.modname(rel).split("."))
            top = [n for stmt in source.tree.body for n in _top_declarations(stmt, self.old)]
            if any(source.name_span(n) == (start, start + len(self.old)) for n in top):
                out.add(Owner(path=module, member=False))
            for chain in _class_chains(source.tree):
                if any(source.name_span(n) == (start, start + len(self.old)) for n in member_declarations(chain[-1], self.old)):
                    out.add(Owner(path=module + tuple(c.name for c in chain), member=True))
        return out

    def _class_path(self, d: Declaration) -> tuple[str, ...]:
        """The qualifying path (module segments, then classes) of the class declaring `d`."""
        module = tuple(self.session.modname(d.rel).split("."))
        tree = self.snapshot.source(d.rel).tree
        for chain in _class_chains(tree) if tree is not None else ():
            source = self.snapshot.source(d.rel)
            if any((span := source.name_span(n)) is not None and span[0] == d.start for n in member_declarations(chain[-1], self.old)):
                return module + tuple(c.name for c in chain)
        return (*module, d.cls)

    def _mention_edits(self) -> None:
        renamed = {(d.rel, d.start) for d in self._declarations if self.is_renamed((d.rel, d.start))}
        rules = MentionRules(
            old=self.old,
            owners=frozenset(self._owners()),
            colliding=frozenset(self._class_path(d) for d in self._declarations if (d.rel, d.start) not in renamed),
        )
        declaring = {rel for rel, _ in self.seeds}
        files: list[tuple[str, list[Mention], bool]] = []
        tables = self.session.tables
        for rel in self.candidates:
            files.append((rel, self._memo(("source_mentions", rel, self.old), partial(self._source_mentions, rel)),
                          rel in declaring))
        for rel in tables.prose():
            found = self._memo(("prose_mentions", rel, self.old), partial(self._prose_mentions, rel))
            if found is not None:
                files.append((rel, found, False))
        for rel, found, is_declaring in files:
            text = self.snapshot.text(rel)
            unhandled = [m for m in found if not self._overlaps(self._targets, rel, m.start, m.end)]
            rewrite, listed = classify(text, unhandled, rules, declaring=is_declaring)
            if self.carves is not None:
                carved = [m for m in rewrite
                          if not rules.qualified(text, m.start) and self.carves.covers(rel, self.old, m.start)]
                rewrite = [m for m in rewrite if m not in carved]
                listed = [*listed, *carved]
            for m in sorted([*rewrite, *listed], key=lambda m: m.start):
                self._file(mention_outcome(rel, m, rewrite=m in rewrite, old=self.old, new=self.new))

    def _memo(self, key: tuple[str, ...], compute: Callable[[], _T]) -> _T:
        assert self._index is not None
        return self._index.memo(key, compute)

    def _source_mentions(self, rel: str) -> list[Mention]:
        source = self.snapshot.source(rel)
        return mentions(source.text, self.old, iter(self.session.tables.regions(rel)), source.line)

    def _prose_mentions(self, rel: str) -> list[Mention] | None:
        """The mentions of a prose file; None when it cannot be read or never spells the old name."""
        try:
            source = self.snapshot.source(rel)
        except (OSError, UnicodeDecodeError, LookupError):
            return None
        if self.old not in source.text:
            return None
        return mentions(source.text, self.old, iter([(0, len(source.text), "prose", False)]), source.line)

    def _compound_names(self) -> None:
        """Each declaration in a project source whose name holds OLD as a word sequence, listed."""
        rels = self.session.python_files()
        found = self._memo(("compounds", self.old), partial(self.session.tables.compounds, rels, self.old))
        for rel, name, span in found:
            if name not in self.renamed_names:
                self._file(compound_outcome(rel, self.snapshot.source(rel), span, name, self.old))

    def _literal_leftovers(self) -> None:
        """Without `--docs`: each string literal exactly OLD that no rule examined, listed; every project file, as an
        escape can spell OLD."""
        for rel in self._files:
            spans = self.session.tables.literals(rel).get(self.old, [])
            handled = partial(self._overlaps, self._examined, rel)
            for outcome in literal_outcomes(rel, self.snapshot.source(rel), self.old, handled, spans) if spans else []:
                self._file(outcome)

    @override
    def prepare(self, index: RunIndex) -> None:
        """The renamed declarations, the member declarations and the stand-in classification."""
        with timed("references"):
            self._index = index
            self._graph = ClassGraph(index, self.session.load)
            self._validate()
            local = self.entry.kind == "local" and bool(self.entry.sites)
            self._files = [self.entry.sites[0][0]] if local else sorted(self.session.python_files())
            self.candidates = [rel for rel in self._files if self.old in self.snapshot.text(rel)]
            self._declarations = self._member_declarations(index)
            self.seeds = self._located(index)
            self._located_sites = set(self.seeds)
            self.member = self.is_member()
            if self.member:
                self._classify(index)
            self._fields = [f for e in self.entries if (f := self._located_field(e)) is not None]

    @override
    def seed(self, facts: TypeFacts) -> None:
        """The declarations only the checker's facts add; raises `UnresolvedBase`."""
        with timed("rules"):
            if self.entry.kind == "parameter" and self.entry.function is not None:
                self._parameter_seeds(facts, self.entry.function)
            for field in self._fields:
                facts.chain(field[0])

    @override
    def rules(self, index: RunIndex, facts: TypeFacts) -> None:
        """Every rule over the index: occurrences, keyed classes, member strings, targets, blind spots."""
        with timed("references"):
            self._index_edits(index)
        with timed("rules"):
            for field in self._fields:
                self._keyed_edits(index, facts, field)
            scan = MemberScan(index, self.old, self.session.load)
            if self.member:
                self._string_member_edits(scan)
            self._target_edits(scan, self.member)
            if self.member:
                with timed("blindspot-scan"):
                    self._blindspot_scan(scan)

    @override
    def finish(self) -> None:
        """The rules that read text only: mentions with `--docs`, else a member's exact-OLD string literals."""
        with timed("rules"):
            if self.options.docs:
                self._mention_edits()
                self._compound_names()
            elif self.member:
                self._literal_leftovers()


def _top_declarations(stmt: ast.stmt, name: str) -> list[ast.AST]:
    """The module-level declarations of `name` a statement makes."""
    if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return [stmt] if stmt.name == name else []
    if isinstance(stmt, ast.Assign):
        targets = stmt.targets
    elif isinstance(stmt, ast.AnnAssign):
        targets = [stmt.target]
    else:
        return []
    return [t for t in targets if isinstance(t, ast.Name) and t.id == name]


def _class_chains(tree: ast.Module) -> Iterator[list[ast.ClassDef]]:
    """Every class with the classes enclosing it, outermost first."""

    def walk(body: list[ast.stmt], chain: list[ast.ClassDef]) -> Iterator[list[ast.ClassDef]]:
        for stmt in body:
            if isinstance(stmt, ast.ClassDef):
                yield [*chain, stmt]
                yield from walk(stmt.body, [*chain, stmt])
            elif isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
                yield from walk(stmt.body, [])

    yield from walk(tree.body, [])
