"""A Python symbol rename: every occurrence the run's occurrence index resolves to a renamed declaration (and those
rope resolves where the checker resolves none), the keyed-class rewrites, member strings and patch targets, and with
`--docs` mentions, as character spans over one snapshot of the project's files; a member rename first checks for blind
spots and stand-ins."""

from __future__ import annotations

import ast
import bisect
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from functools import partial
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict
from rope.base import libutils, pynamesdef
from rope.base.fscommands import read_str_coding
from rope.base.project import Project
from rope.base.pyobjectsdef import PyClass, PyFunction, PyModule
from rope.refactor import occurrences
from rope.refactor.rename import Rename, _is_local
from typing_extensions import override

from living_architecture.contract import message
from living_architecture.lang import Occurrence, Span
from living_architecture.refactor.hierarchy import ClassGraph, ClassKey
from living_architecture.refactor.keyed import (
    Bindings,
    ClassRef,
    KeyedRename,
    TypeFacts,
    declares_alias,
    field_assignment,
)
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
from living_architecture.refactor.python_source import SourceFile
from living_architecture.refactor.rope_patches import every_parameter
from living_architecture.refactor.routing import language_files
from living_architecture.refactor.sites import Site
from living_architecture.refactor.static_resolver import Module
from living_architecture.refactor.text_edits import TextEdit
from living_architecture.refactor.text_tables import TextTables
from living_architecture.refactor.timings import timed


def _normalize(text: str) -> str:
    """The text as rope reads it."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


class Snapshot:
    """Each project file read once: its bytes, encoding, text and syntax tree."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._data: dict[str, bytes] = {}
        self._texts: dict[str, str] = {}
        self._encodings: dict[str, str] = {}
        self._sources: dict[str, SourceFile] = {}

    def text(self, rel: str) -> str:
        if rel not in self._texts:
            data = (self.root / rel).read_bytes()
            encoding = read_str_coding(data) or "utf-8"
            self._data[rel] = data
            self._encodings[rel] = encoding
            self._texts[rel] = data.decode(encoding)
        return self._texts[rel]

    def source(self, rel: str) -> SourceFile:
        if rel not in self._sources:
            self._sources[rel] = SourceFile(self.root / rel, self.text(rel))
        return self._sources[rel]

    def encode(self, rel: str, text: str) -> bytes:
        return text.encode(self._encodings[rel])

    def decode(self, rel: str, data: bytes) -> str:
        """`data` written to `rel`, as text."""
        self.text(rel)
        return data.decode(self._encodings[rel])

    def data(self, rel: str) -> bytes:
        """The bytes `rel` was read as."""
        self.text(rel)
        return self._data[rel]


class Session:
    """One refactor's view of the project: rope's project, the snapshot, and files read outside it."""

    def __init__(self, project: Project) -> None:
        self.project = project
        self.root = Path(project.address).resolve()
        self.snapshot = Snapshot(self.root)
        self.tables = TextTables(self.root, self.snapshot.source)
        self._outside: dict[Path, SourceFile | None] = {}

    def rel(self, path: Path) -> str | None:
        return path.relative_to(self.root).as_posix() if path.is_relative_to(self.root) else None

    def load(self, path: Path) -> SourceFile | None:
        if path.is_relative_to(self.root) and path.suffix in (".py", ".pyi") and path.is_file():
            return self.snapshot.source(path.relative_to(self.root).as_posix())
        if path not in self._outside:
            try:
                with open(path, encoding="utf-8", newline="") as fh:
                    self._outside[path] = SourceFile(path, fh.read())
            except (OSError, UnicodeDecodeError):
                self._outside[path] = None
        return self._outside[path]

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


class RopeSites:
    """The occurrences the checker resolves to no declaration, each evaluated by rope at most once per run."""

    def __init__(self, project: Project, snapshot: Snapshot) -> None:
        self.project = project
        self.snapshot = snapshot
        self._tools: dict[str, Any] = {}
        self._sites: dict[tuple[str, int], Any] = {}

    def _occurrence(self, rel: str, start: int) -> Any:
        if rel not in self._tools:
            self._tools[rel] = occurrences._OccurrenceToolsCreator(  # pyright: ignore[reportPrivateUsage]
                self.project, resource=self.project.get_resource(rel), docs=False)
        if (rel, start) not in self._sites:
            self._sites[rel, start] = occurrences.Occurrence(self._tools[rel], _rope_offset(self.snapshot.text(rel), start))
        return self._sites[rel, start]

    def matches(self, finder: Any, rel: str, start: int) -> bool:
        """Whether rope's `finder` accepts the occurrence starting at `start` of `rel`, as its own search would."""
        occurrence = self._occurrence(rel, start)
        for found in finder.filters:
            result = found(occurrence)
            if result is not None:
                return bool(result)
        return False


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


class Declaration(BaseModel):
    """A class member named like the renamed symbol: its file, name span, line and class."""

    model_config = ConfigDict(frozen=True)

    rel: str
    start: int
    line: int
    cls: str


def _rope_offset(raw: str, offset: int) -> int:
    """`offset` in `raw` as an offset in rope's newline-normalized text."""
    return offset - raw.count("\r\n", 0, offset)


class MapRename(ABC):
    """A rename map entry's phases, run over all entries in turn: `prepare`, `seed` and `rules` (on the run's
    occurrence index), `finish`."""

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
    def check_conflicts(self, edits: list[TextEdit]) -> None: ...


class SymbolRename(MapRename):
    """A rename of a symbol other than a module, located by rope's `renamer` at `site` (a file and an offset in its
    text): `prepare` finds the renamed declarations and the stand-ins, `rules` the edits, `finish` the mentions and
    leftovers."""

    def __init__(self, session: Session, renamer: Rename, new_name: str, options: RenameOptions | None = None, *,
                 site: tuple[str, int], rope_sites: RopeSites | None = None) -> None:
        self.session = session
        self.site = site
        self.rope_sites = rope_sites or RopeSites(session.project, session.snapshot)
        self._index: RunIndex | None = None
        self._graph: ClassGraph | None = None
        self._located_sites: set[tuple[str, int]] = set()
        self.project = session.project
        self.renamer = renamer
        self.options = options or RenameOptions()
        self.old: str = renamer.get_old_name()
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
        self.renamers: list[Rename] = [renamer]
        self.blindspots: list[Finding] = []
        self.stand_ins: list[Finding] = []
        self.leftovers: list[Finding] = []
        self._declarations: list[Declaration] = []
        self._unclassified: list[Declaration] = []
        self._examined: dict[str, list[tuple[int, int]]] = {}
        self._targets: dict[str, list[tuple[int, int]]] = {}
        self._in_hierarchy = self.options.in_hierarchy
        self._unsure = self.options.unsure

    def _finder(self, renamer: Rename) -> Any:
        return occurrences.create_finder(
            self.project,
            self.old,
            renamer.old_pyname,
            docs=False,
            instance=renamer.old_instance,
            in_hierarchy=self._in_hierarchy and renamer.is_method(),
        )

    def _validate(self) -> None:
        self.renamer.validate_changes(self.new)

    def _project_declarations(self, found: Occurrence | None) -> set[tuple[str, int]]:
        if found is None:
            return set()
        return {(rel, d.span.start) for d in found.declarations if (rel := self.session.rel(d.span.path)) is not None}

    def _located(self, index: RunIndex) -> set[tuple[str, int]]:
        """An import alias's own binding at the entry's site, else the declarations the checker resolves the site to;
        where it resolves none in the project, those on the line rope finds the symbol defined at."""
        rel, offset = self.site
        at = index.at(self.root / rel, self.old, offset)
        if at is not None and at.kind == "alias":
            return {(rel, at.span.start)}
        found = self._project_declarations(at)
        if found:
            return found
        location = self.renamer.old_pyname.get_definition_location() if self.renamer.old_pyname is not None else None
        module, line = location or (None, None)
        resource = module.get_resource() if isinstance(module, PyModule) else None
        if resource is None or line is None:
            return set()
        source = self.snapshot.source(resource.path)
        return {(resource.path, s) for s, e in _declarations(source) if source.line(s) == line and source.text[s:e] == self.old}

    def _member_declarations(self) -> list[Declaration]:
        """Every declaration of a class member named like the symbol, in the candidate files."""
        out: list[Declaration] = []
        for rel in self.candidates:
            source = self.snapshot.source(rel)
            for cls in source.of_type(ast.ClassDef):
                for node in member_declarations(cls, self.old):
                    span = source.name_span(node)
                    if span is not None:
                        out.append(Declaration(rel=rel, start=span[0], line=source.line(span[0]), cls=cls.name))
        return sorted(out, key=lambda d: (d.rel, d.start))

    @override
    def header(self) -> str:
        return message("refactor.rename-header", old=self.old, new=self.new)

    def renamed_members(self) -> list[tuple[tuple[str, int], tuple[str, int]]]:
        """Each member declaration this rename's edits rename, with its class's file and `class` line."""
        if not self.member:
            return []
        starts = {(e.path, e.start) for e in self.edits}
        out: list[tuple[tuple[str, int], tuple[str, int]]] = []
        for d in self._declarations:
            source = self.snapshot.source(d.rel)
            if (d.rel, d.start) not in starts or source.tree is None:
                continue
            owner = next((cls for cls in source.of_type(ast.ClassDef) if any(
                (span := source.name_span(n)) is not None and span[0] == d.start
                for n in member_declarations(cls, self.old))), None)
            if owner is not None:
                out.append(((d.rel, d.start), (d.rel, owner.lineno)))
        return out

    def is_member(self) -> bool:
        """The symbol is declared in a class body (or as a `self.` attribute): a declaration rope renames is one."""
        if isinstance(self.renamer.old_pyname, pynamesdef.ParameterName):
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
        """The member declarations rope renames with the member declared at `sites` when the hierarchy is on: for a
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
        return self._hierarchy(self._index, self._located_sites, self.renamer.is_method())

    def _own(self, index: RunIndex, d: Declaration) -> set[tuple[str, int]]:
        """The declarations of the member declared at `d`, as the checker resolves its name there."""
        return self._project_declarations(index.at(self.root / d.rel, self.old, d.start)) | {(d.rel, d.start)}

    def _classify(self, index: RunIndex) -> None:
        """The renamed declarations: the hierarchy (with it on) and every `--with` stand-in's; record the stand-ins left
        unclassified."""
        hierarchy = self._hierarchy(index, self.seeds, self.renamer.is_method())
        stand_ins = [d for d in self._declarations if (d.rel, d.start) not in hierarchy]
        renamed = set(hierarchy) | self.seeds if self._in_hierarchy else set(self.seeds)
        classified: set[tuple[str, int]] = set()
        for raw, joined in [*((s, True) for s in self.options.with_sites), *((s, False) for s in self.options.without_sites)]:
            site = Site.parse(raw, self.root, base=self.root)
            matched = [d for d in stand_ins if site.line is not None and site.covers(d.rel, d.line)]
            if matched:
                self.matched_sites.add(raw)
            for d in matched:
                renamer = Rename(self.project, self.project.get_resource(d.rel), _rope_offset(self.snapshot.text(d.rel), d.start))
                theirs = self._hierarchy(index, {(d.rel, d.start)}, renamer.is_method())
                classified |= theirs | {(d.rel, d.start)}
                if joined:
                    self.renamers.append(renamer)
                    renamed |= theirs | {(d.rel, d.start)} if self._in_hierarchy else self._own(index, d)
        self._unclassified = [d for d in stand_ins if (d.rel, d.start) not in classified]
        self.seeds = renamed

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
        or alias the checker resolves to nothing that rope resolves to a renamed symbol."""
        unresolved: list[tuple[str, Occurrence]] = []
        for rel in self.candidates:
            for o in index.occurrences(self.root / rel, self.old):
                if self._renames(o) or (self._unsure and o.kind == "member" and o.receiver is not None):
                    self.edits.append(TextEdit(path=rel, start=o.span.start, end=o.span.end, new_text=self.new))
                elif not o.declarations and o.kind in ("name", "import", "alias"):
                    unresolved.append((rel, o))
        if not unresolved:
            return
        finders = [self._finder(r) for r in self.renamers]
        for rel, o in unresolved:
            if any(self.rope_sites.matches(f, rel, o.span.start) for f in finders):
                self.edits.append(TextEdit(path=rel, start=o.span.start, end=o.span.end, new_text=self.new))

    def _renames(self, o: Occurrence) -> bool:
        """`o` resolves to a renamed declaration or through a renamed import alias (a keyword only through one that
        takes keywords)."""
        spans = [*(d.span for d in o.declarations), *o.bindings]
        hits = {(r, s.start) for s in spans if (r := self.session.rel(s.path)) is not None} & self.seeds
        if o.kind == "keyword":
            hits -= self.keywordless
        return bool(hits)

    def _located_field(self, renamer: Rename) -> tuple[ClassRef, ast.AnnAssign | ast.Assign, Span] | None:
        pyname = renamer.old_pyname
        location = pyname.get_definition_location() if pyname is not None else None
        module, line = location or (None, None)
        resource = module.get_resource() if isinstance(module, PyModule) else None
        if resource is None or resource.path not in self.candidates:
            return None
        source = self.snapshot.source(resource.path)
        lines = [line] if line is not None else sorted({source.line(o) for rel, o in self.seeds if rel == resource.path})
        return next((f for n in lines if (f := _field_of(source, n, self.old)) is not None), None)

    def _keyed_edits(self, facts: TypeFacts, field: tuple[ClassRef, ast.AnnAssign | ast.Assign, Span]) -> None:
        owner, stmt, declared = field
        if facts.chain(owner).kind is None:
            return
        keyed = KeyedRename(facts, self.old, self.new, {(declared.path, declared.start)}, aliased=declares_alias(stmt))
        bindings = Bindings()
        for rel in self.candidates:
            keyed.scan(self.snapshot.source(rel), rel, bindings)
        self.edits += keyed.edits
        self.edits += bindings.edits()

    def _function_at(self, fn: PyFunction) -> tuple[str, Function] | None:
        """rope's function `fn` as a node of its file's snapshot."""
        module = fn.get_module()
        resource = module.get_resource() if isinstance(module, PyModule) else None
        if resource is None or resource.path not in self.candidates:
            return None
        node = fn.get_ast()
        found = (
            n
            for n in self.snapshot.source(resource.path).nodes
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and (n.lineno, n.col_offset, n.name) == (node.lineno, node.col_offset, node.name)
        )
        return next(((resource.path, n) for n in found), None)

    def _method_declarations(self, fn: PyFunction) -> list[tuple[str, Function]]:
        """The declarations a rename of method `fn` renames: its own, and with the hierarchy on those of every class
        whose roots for its name meet its class's."""
        assert self._graph is not None
        name = fn.get_name()
        located = self._function_at(fn)
        if located is None:
            return []
        rel, node = located
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

    def _parameter_declarations(self, facts: TypeFacts, fn: PyFunction) -> list[tuple[str, SourceFile, Function, ast.arg]]:
        """The renamed parameters: those named `old` of the method hierarchy's declarations and their overload groups."""
        located = self._function_at(fn)
        if located is None:
            return []
        defs = [located]
        if isinstance(fn.parent, PyClass):
            defs += self._method_declarations(fn)
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

    def _parameter_seeds(self, facts: TypeFacts, fn: PyFunction) -> None:
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
        folders = SourceFolders([Path(f.real_path) for f in self.project.get_source_folders()])
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
            module = tuple(libutils.modname(self.project.get_resource(rel)).split("."))
            top = [n for stmt in source.tree.body for n in _top_declarations(stmt, self.old)]
            if any(source.name_span(n) == (start, start + len(self.old)) for n in top):
                out.add(Owner(path=module, member=False))
            for chain in _class_chains(source.tree):
                if any(source.name_span(n) == (start, start + len(self.old)) for n in member_declarations(chain[-1], self.old)):
                    out.add(Owner(path=module + tuple(c.name for c in chain), member=True))
        return out

    def _class_path(self, d: Declaration) -> tuple[str, ...]:
        """The qualifying path (module segments, then classes) of the class declaring `d`."""
        module = tuple(libutils.modname(self.project.get_resource(d.rel)).split("."))
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
            source = self.snapshot.source(rel)
            files.append((rel, mentions(source.text, self.old, iter(tables.regions(rel)), source.line), rel in declaring))
        for rel in tables.prose():
            try:
                source = self.snapshot.source(rel)
            except (OSError, UnicodeDecodeError, LookupError):
                continue
            if self.old in source.text:
                files.append((rel, mentions(source.text, self.old, iter([(0, len(source.text), "prose", False)]), source.line), False))
        for rel, found, is_declaring in files:
            text = self.snapshot.text(rel)
            unhandled = [m for m in found if not self._overlaps(self._targets, rel, m.start, m.end)]
            rewrite, listed = classify(text, unhandled, rules, declaring=is_declaring)
            for m in sorted([*rewrite, *listed], key=lambda m: m.start):
                self._file(mention_outcome(rel, m, rewrite=m in rewrite, old=self.old, new=self.new))

    def _compound_names(self) -> None:
        """Each declaration in a project source whose name holds OLD as a word sequence, listed."""
        rels = [path.relative_to(self.root).as_posix() for path in language_files(self.root, "python")]
        for rel, name, span in self.session.tables.compounds(rels, self.old):
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
            pyname = self.renamer.old_pyname
            local = _is_local(pyname)
            self._files = [self.renamer.resource.path] if local else sorted(
                path.relative_to(self.root).as_posix() for path in language_files(self.root, "python"))
            self.candidates = [rel for rel in self._files if self.old in self.snapshot.text(rel)]
            self._declarations = self._member_declarations()
            self.seeds = self._located(index)
            self._located_sites = set(self.seeds)
            self.member = self.is_member()
            if self.member:
                self._classify(index)
            self._fields = [f for r in self.renamers if (f := self._located_field(r)) is not None]

    @override
    def seed(self, facts: TypeFacts) -> None:
        """The declarations only the checker's facts add; raises `UnresolvedBase`."""
        with timed("rules"):
            pyname = self.renamer.old_pyname
            if isinstance(pyname, pynamesdef.ParameterName):
                self._parameter_seeds(facts, pyname.pyfunction)
            for field in self._fields:
                facts.chain(field[0])

    @override
    def rules(self, index: RunIndex, facts: TypeFacts) -> None:
        """Every rule over the index: occurrences, keyed classes, member strings, targets, blind spots."""
        with timed("references"):
            self._index_edits(index)
        with timed("rules"):
            for field in self._fields:
                self._keyed_edits(facts, field)
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

    @override
    def check_conflicts(self, edits: list[TextEdit]) -> None:
        """`NameConflict` where one of `edits` (this rename's, merged) meets the new name."""
        if not self.check_names:
            return
        for rel in sorted({e.path for e in edits}):
            _conflict(self.snapshot.source(rel), rel, [e for e in edits if e.path == rel], self.old, self.new)


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
