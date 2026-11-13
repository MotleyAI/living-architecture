"""A Python symbol rename: rope's edits, every reference basedpyright resolves to each renamed declaration and the
keyed-class rewrites, as character spans over one snapshot of the project's files."""

from __future__ import annotations

import ast
import bisect
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rope.base.change import ChangeContents, ChangeSet
from rope.base.fscommands import read_str_coding
from rope.base.project import Project
from rope.base.pyobjectsdef import PyModule
from rope.base.resources import File
from rope.refactor import occurrences
from rope.refactor.rename import Rename, _is_local

from living_architecture.lang import LanguageServer, Span
from living_architecture.refactor.keyed import (
    Bindings,
    ClassRef,
    KeyedRename,
    TypeFacts,
    declares_alias,
    field_assignment,
)
from living_architecture.refactor.move_edits import NameConflict
from living_architecture.refactor.python_source import SourceFile
from living_architecture.refactor.text_edits import TextEdit, apply_edits, merge_edits


class FileChanged(Exception):
    """The file at `path` changed after the rename read it."""

    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.path = path


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

    def changed(self, rel: str) -> bool:
        path = self.root / rel
        return not path.is_file() or path.read_bytes() != self._data[rel]


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


class SymbolRename:
    """A rename of a symbol other than a module: computes its edits, then prints and optionally writes them."""

    def __init__(self, project: Project, renamer: Rename, new_name: str, *, in_hierarchy: bool, unsure: bool) -> None:
        self.project = project
        self.renamer = renamer
        self.old: str = renamer.get_old_name()
        self.new = new_name
        self.root = Path(project.address).resolve()
        self.snapshot = Snapshot(self.root)
        self.edits: list[TextEdit] = []
        self.seeds: set[tuple[str, int]] = set()
        self.candidates: list[str] = []
        self._in_hierarchy = in_hierarchy
        self._unsure = unsure
        self._outside: dict[Path, SourceFile | None] = {}

    def _rope_edits(self) -> None:
        pyname = self.renamer.old_pyname
        resources: list[File] = [self.renamer.resource] if _is_local(pyname) else self.project.get_python_files()
        self.renamer.validate_changes(self.new)
        finder = occurrences.create_finder(
            self.project,
            self.old,
            pyname,
            unsure=(lambda *_: True) if self._unsure else None,
            docs=False,
            instance=self.renamer.old_instance,
            in_hierarchy=self._in_hierarchy and self.renamer.is_method(),
        )
        for file_ in sorted(resources, key=lambda r: r.path):
            text = file_.read()
            if self.old not in text:
                continue
            rel = file_.path
            raw = self.snapshot.text(rel)
            if _normalize(raw) != text:
                raise FileChanged(rel)
            self.candidates.append(rel)
            to_raw = _raw_offsets(raw)
            declarations = _declarations(self.snapshot.source(rel))
            for occurrence in finder.find_occurrences(resource=file_):
                start, end = (to_raw(i) for i in occurrence.get_word_range())
                self.edits.append(TextEdit(path=rel, start=start, end=end, new_text=self.new))
                if (start, end) in declarations:
                    self.seeds.add((rel, start))

    def _load(self, path: Path) -> SourceFile | None:
        if path.is_relative_to(self.root):
            rel = path.relative_to(self.root).as_posix()
            if rel in self.candidates or (path.suffix in (".py", ".pyi") and path.is_file()):
                return self.snapshot.source(rel)
        if path not in self._outside:
            try:
                with open(path, encoding="utf-8", newline="") as fh:
                    self._outside[path] = SourceFile(path, fh.read())
            except (OSError, UnicodeDecodeError):
                self._outside[path] = None
        return self._outside[path]

    def _read(self, path: Path) -> str:
        source = self._load(path)
        if source is None:
            raise OSError(path)
        return source.text

    def _reference_edits(self, server: LanguageServer) -> None:
        candidates = set(self.candidates)
        for rel, start in sorted(self.seeds):
            for span in server.references(self.root / rel, start):
                if not span.path.is_relative_to(self.root):
                    continue
                ref = span.path.relative_to(self.root).as_posix()
                if ref in candidates and self.snapshot.text(ref)[span.start : span.end] == self.old:
                    self.edits.append(TextEdit(path=ref, start=span.start, end=span.end, new_text=self.new))

    def _located_field(self) -> tuple[ClassRef, ast.AnnAssign | ast.Assign, Span] | None:
        pyname = self.renamer.old_pyname
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

    def compute(self) -> None:
        """Every edit of the rename; raises `LanguageServerError`, `UnresolvedBase`, `NameConflict` or `FileChanged`."""
        self._rope_edits()
        field = self._located_field()
        with LanguageServer(self.root, read=self._read) as server:
            for rel in self.candidates:
                server.open(self.root / rel, self.snapshot.text(rel))
            facts = TypeFacts(server, self._load)
            if field is not None:
                facts.chain(field[0])
            self._reference_edits(server)
            if field is not None:
                self._keyed_edits(facts, field)
        self.edits = merge_edits(self.edits)
        for rel in sorted({e.path for e in self.edits}):
            _conflict(self.snapshot.source(rel), rel, [e for e in self.edits if e.path == rel], self.old, self.new)

    def changes(self) -> tuple[ChangeSet, dict[str, str]]:
        """The rope change set to print, and each touched file's new text."""
        changes = ChangeSet(f"Renaming <{self.old}> to <{self.new}>")
        texts: dict[str, str] = {}
        for rel in sorted({e.path for e in self.edits}):
            raw = self.snapshot.text(rel)
            texts[rel] = apply_edits(raw, [e for e in self.edits if e.path == rel])
            if texts[rel] == raw:
                del texts[rel]
                continue
            resource: Any = self.project.get_resource(rel)
            changes.add_change(ChangeContents(resource, _normalize(texts[rel]), old_contents=_normalize(raw)))
        return changes, texts

    def verify(self, texts: dict[str, str]) -> None:
        """Raise `FileChanged` when a file to write changed since it was read."""
        for rel in texts:
            if self.snapshot.changed(rel):
                raise FileChanged(rel)

    def write(self, texts: dict[str, str]) -> None:
        """Write every new text, or nothing when a file changed since it was read."""
        self.verify(texts)
        for rel, text in texts.items():
            (self.root / rel).write_bytes(self.snapshot.encode(rel, text))
