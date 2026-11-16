"""A Python symbol rename: rope's edits, every reference basedpyright resolves to each renamed declaration, the
keyed-class rewrites, member strings and patch targets, and with `--docs` mentions, as character spans over one
snapshot of the project's files; a member rename first checks for blind spots and stand-ins."""

from __future__ import annotations

import ast
import bisect
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict
from rope.base import libutils, pynamesdef
from rope.base.fscommands import read_str_coding
from rope.base.project import Project
from rope.base.pyobjectsdef import PyClass, PyFunction, PyModule
from rope.base.resources import File
from rope.refactor import occurrences
from rope.refactor.rename import Rename, _is_local
from typing_extensions import override

from living_architecture.config import source_files
from living_architecture.contract import manifest, message
from living_architecture.lang import LanguageServer, Span
from living_architecture.refactor.compound import is_compound
from living_architecture.refactor.keyed import (
    Bindings,
    ClassRef,
    KeyedRename,
    TypeFacts,
    declares_alias,
    field_assignment,
)
from living_architecture.refactor.member_scan import FormCall, MemberScan
from living_architecture.refactor.members import classes, member_declarations
from living_architecture.refactor.mentions import (
    Mention,
    MentionRules,
    Owner,
    classify,
    mentions,
    source_regions,
)
from living_architecture.refactor.move_edits import NameConflict
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
from living_architecture.refactor.writer import FileChanged


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


def _raw_offsets(raw: str) -> Callable[[int], int]:
    """Maps an offset in rope's newline-normalized text to the same character in `raw`."""
    positions: list[int] = []
    index = raw.find("\r\n")
    while index != -1:
        positions.append(index - len(positions))
        index = raw.find("\r\n", index + 2)
    return lambda n: n + bisect.bisect_left(positions, n)


def _declarations(source: SourceFile) -> set[tuple[int, int]]:
    """The spans of every name `source` declares: defs, classes, parameters and assignment targets."""
    if source.tree is None:
        return set()
    out: set[tuple[int, int]] = set()
    for node in ast.walk(source.tree):
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
    classes = (n for n in ast.walk(source.tree) if isinstance(n, ast.ClassDef))
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

    for node in ast.walk(source.tree):
        items = _named_items(source, node)
        if any(name == new for name, _, _ in items):
            line = next((line for name, line, span in items if name == old and edited(span)), None)
            if line is not None:
                raise NameConflict(new, rel, line)


Function = ast.FunctionDef | ast.AsyncFunctionDef


def _parameter(fn: Function, name: str) -> ast.arg | None:
    """`fn`'s parameter `name`, of any kind."""
    return next((a for a in every_parameter(fn.args) if a.arg == name), None)


def _same_named(tree: ast.Module, fn: Function) -> list[Function]:
    """The defs named like `fn` in the module or class body holding it; `[fn]` in any other body."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef)) and any(stmt is fn for stmt in node.body):
            return [s for s in node.body if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)) and s.name == fn.name]
    return [fn]


def _keyword_spans(source: SourceFile) -> set[tuple[int, int]]:
    """The name spans of every call keyword in `source`."""
    if source.tree is None:
        return set()
    return {s for k in ast.walk(source.tree) if isinstance(k, ast.keyword) and (s := source.name_span(k)) is not None}


class RenameOptions(BaseModel):
    """How a symbol rename runs: hierarchy, unsure occurrences, the blind-spot override, stand-in classifications,
    kept sites and the mention scan."""

    model_config = ConfigDict(frozen=True)

    in_hierarchy: bool = True
    unsure: bool = False
    allow_blindspots: bool = False
    with_sites: tuple[str, ...] = ()
    without_sites: tuple[str, ...] = ()
    keep: tuple[str, ...] = ()
    docs: bool = False


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
    """A rename map entry's phases, run over all entries in turn: `prepare`, `seed` and `rules` (on the shared
    language server), `finish`."""

    @abstractmethod
    def header(self) -> str: ...

    @abstractmethod
    def stand_in_findings(self) -> list[Finding]: ...

    @abstractmethod
    def prepare(self) -> None: ...

    @abstractmethod
    def seed(self, facts: TypeFacts) -> None: ...

    @abstractmethod
    def rules(self, server: LanguageServer, facts: TypeFacts) -> None: ...

    @abstractmethod
    def finish(self) -> None: ...

    @abstractmethod
    def check_conflicts(self, edits: list[TextEdit]) -> None: ...


class SymbolRename(MapRename):
    """A rename of a symbol other than a module: `prepare` computes rope's edits and the stand-ins, `finish` the
    mentions and leftovers."""

    def __init__(self, session: Session, renamer: Rename, new_name: str, options: RenameOptions | None = None) -> None:
        self.session = session
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

    def _finder(self, renamer: Rename, in_hierarchy: bool) -> Any:
        return occurrences.create_finder(
            self.project,
            self.old,
            renamer.old_pyname,
            unsure=(lambda *_: True) if self._unsure else None,
            docs=False,
            instance=renamer.old_instance,
            in_hierarchy=in_hierarchy and renamer.is_method(),
        )

    def _occurrences(self, renamer: Rename, in_hierarchy: bool) -> Iterator[tuple[str, int, int]]:
        """rope's occurrences of `renamer`'s symbol in the candidate files, as raw spans."""
        finder = self._finder(renamer, in_hierarchy)
        for rel in self.candidates:
            to_raw = _raw_offsets(self.snapshot.text(rel))
            for occurrence in finder.find_occurrences(resource=cast(File, self.project.get_resource(rel))):
                start, end = (to_raw(i) for i in occurrence.get_word_range())
                yield rel, start, end

    def _rope_edits(self) -> None:
        pyname = self.renamer.old_pyname
        resources: list[File] = [self.renamer.resource] if _is_local(pyname) else [
            cast(File, self.project.get_resource(path.relative_to(self.root).as_posix())) for path in language_files(self.root, "python")
        ]
        self._validate()
        self._files = sorted(r.path for r in resources)
        for file_ in sorted(resources, key=lambda r: r.path):
            text = file_.read()
            if self.old not in text:
                continue
            rel = file_.path
            if _normalize(self.snapshot.text(rel)) != text:
                raise FileChanged(rel)
            self.candidates.append(rel)
        for renamer in self.renamers:
            self._add_occurrences(renamer)

    def _validate(self) -> None:
        self.renamer.validate_changes(self.new)

    def _add_occurrences(self, renamer: Rename) -> None:
        declarations: dict[str, set[tuple[int, int]]] = {}
        for rel, start, end in self._occurrences(renamer, self._in_hierarchy):
            self.edits.append(TextEdit(path=rel, start=start, end=end, new_text=self.new))
            if rel not in declarations:
                declarations[rel] = _declarations(self.snapshot.source(rel))
            if (start, end) in declarations[rel]:
                self.seeds.add((rel, start))

    def _member_declarations(self) -> list[Declaration]:
        """Every declaration of a class member named like the symbol, in the candidate files."""
        out: list[Declaration] = []
        for rel in self.candidates:
            source = self.snapshot.source(rel)
            for cls in classes(source.tree) if source.tree is not None else ():
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
            owner = next((cls for cls in classes(source.tree) if any(
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

    def _hierarchy(self, renamer: Rename) -> set[tuple[str, int]]:
        """The member declarations rope renames with `renamer`'s symbol when the hierarchy is on."""
        spans = {(d.rel, d.start) for d in self._declarations}
        return {(rel, start) for rel, start, _ in self._occurrences(renamer, True) if (rel, start) in spans}

    def _classify(self) -> None:
        """Join every `--with` stand-in's hierarchy; record the stand-ins left unclassified."""
        hierarchy = self._hierarchy(self.renamer)
        stand_ins = [d for d in self._declarations if (d.rel, d.start) not in hierarchy]
        classified: set[tuple[str, int]] = set()
        for raw, joined in [*((s, True) for s in self.options.with_sites), *((s, False) for s in self.options.without_sites)]:
            site = Site.parse(raw, self.root, base=self.root)
            matched = [d for d in stand_ins if site.line is not None and site.covers(d.rel, d.line)]
            if matched:
                self.matched_sites.add(raw)
            for d in matched:
                raw_text = self.snapshot.text(d.rel)
                renamer = Rename(self.project, self.project.get_resource(d.rel), _rope_offset(raw_text, d.start))
                classified |= self._hierarchy(renamer) | {(d.rel, d.start)}
                if joined:
                    self.renamers.append(renamer)
        self._unclassified = [d for d in stand_ins if (d.rel, d.start) not in classified]

    @override
    def stand_in_findings(self) -> list[Finding]:
        """The unclassified stand-ins no entry of the map renames."""
        return [
            Finding(path=d.rel, line=d.line, col=d.start, text=message(
                "refactor.stand-in", path=d.rel, line=d.line, cls=d.cls, attr=self.old))
            for d in self._unclassified
            if not self.is_renamed((d.rel, d.start))
        ]

    def _reference_edits(self, server: LanguageServer) -> None:
        candidates = set(self.candidates)
        for rel, start in sorted(self.seeds):
            for span in server.references(self.root / rel, start):
                ref = self.session.rel(span.path)
                if ref is None or ref not in candidates or self.snapshot.text(ref)[span.start : span.end] != self.old:
                    continue
                if (rel, start) in self.keywordless and (span.start, span.end) in _keyword_spans(self.snapshot.source(ref)):
                    continue
                self.edits.append(TextEdit(path=ref, start=span.start, end=span.end, new_text=self.new))

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
        tree = self.snapshot.source(resource.path).tree
        found = (
            n
            for n in (ast.walk(tree) if tree is not None else ())
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and (n.lineno, n.col_offset, n.name) == (node.lineno, node.col_offset, node.name)
        )
        return next(((resource.path, n) for n in found), None)

    def _method_declarations(self, fn: PyFunction, cls: PyClass) -> list[tuple[str, Function]]:
        """The declarations a rename of method `fn` renames."""
        name = fn.get_name()
        finder = occurrences.create_finder(self.project, name, cls[name], docs=False, in_hierarchy=self._in_hierarchy)
        out: list[tuple[str, Function]] = []
        for rel in self.candidates:
            source = self.snapshot.source(rel)
            if source.tree is None or name not in source.text:
                continue
            defs = {
                source.name_span(n): n
                for n in ast.walk(source.tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
            }
            to_raw = _raw_offsets(source.text)
            for occurrence in finder.find_occurrences(resource=cast(File, self.project.get_resource(rel))):
                start, end = (to_raw(i) for i in occurrence.get_word_range())
                if (node := defs.get((start, end))) is not None:
                    out.append((rel, node))
        return out

    def _parameter_declarations(self, facts: TypeFacts, fn: PyFunction) -> list[tuple[str, SourceFile, Function, ast.arg]]:
        """The renamed parameters: those named `old` of the method hierarchy's declarations and their overload groups."""
        located = self._function_at(fn)
        if located is None:
            return []
        defs = [located]
        if isinstance(fn.parent, PyClass):
            defs += self._method_declarations(fn, fn.parent)
        seen: set[tuple[str, int, int]] = set()
        out: list[tuple[str, SourceFile, Function, ast.arg]] = []
        for rel, node in defs:
            source = self.snapshot.source(rel)
            assert source.tree is not None
            group = _same_named(source.tree, node)
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
            for call, (_, definitions) in zip(calls, scan.probe(path, source, calls), strict=True):
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
        for rel in self.candidates:
            source = self.snapshot.source(rel)
            files.append((rel, mentions(source.text, self.old, source_regions(source), source.line), rel in declaring))
        extensions = tuple(manifest()["dr-refactor"]["prose_extensions"])
        for rel in sorted(source_files(self.root, [])):
            if not rel.endswith(extensions):
                continue
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
        for path in language_files(self.root, "python"):
            rel = path.relative_to(self.root).as_posix()
            try:
                source = self.snapshot.source(rel)
            except (OSError, UnicodeDecodeError, LookupError):
                continue
            if source.tree is None:
                continue
            for node in ast.walk(source.tree):
                name = _declared_name(node)
                span = source.name_span(node) if name is not None else None
                if name is not None and span is not None and name not in self.renamed_names and is_compound(name, self.old):
                    self._file(compound_outcome(rel, source, span, name, self.old))

    def _literal_leftovers(self) -> None:
        """Without `--docs`: each string literal exactly OLD that no rule examined, listed; every project file, as an
        escape can spell OLD."""
        for rel in self._files:
            source = self.snapshot.source(rel)
            for outcome in literal_outcomes(rel, source, self.old, lambda s, e, rel=rel: self._overlaps(self._examined, rel, s, e)):
                self._file(outcome)

    @override
    def prepare(self) -> None:
        """rope's edits, the member declarations and the stand-in classification; raises `FileChanged`."""
        self._rope_edits()
        self._declarations = self._member_declarations()
        self.member = self.is_member()
        if self.member:
            self._classify()
            for renamer in self.renamers[1:]:
                self._add_occurrences(renamer)
        self._fields = [f for r in self.renamers if (f := self._located_field(r)) is not None]

    @override
    def seed(self, facts: TypeFacts) -> None:
        """The declarations only the checker's facts add; raises `UnresolvedBase`."""
        pyname = self.renamer.old_pyname
        if isinstance(pyname, pynamesdef.ParameterName):
            self._parameter_seeds(facts, pyname.pyfunction)
        for field in self._fields:
            facts.chain(field[0])

    @override
    def rules(self, server: LanguageServer, facts: TypeFacts) -> None:
        """Every rule that asks the checker: references, keyed classes, member strings, targets, blind spots."""
        self._reference_edits(server)
        for field in self._fields:
            self._keyed_edits(facts, field)
        scan = MemberScan(server, self.old, self.session.load)
        if self.member:
            self._string_member_edits(scan)
        self._target_edits(scan, self.member)
        if self.member:
            self._blindspot_scan(scan)

    @override
    def finish(self) -> None:
        """The rules that read text only: mentions with `--docs`, else a member's exact-OLD string literals."""
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


def _declared_name(node: ast.AST) -> str | None:
    """The name a def, class, parameter or assignment target declares."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.arg):
        return node.arg
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        return node.id
    if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
        return node.attr
    return None


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
