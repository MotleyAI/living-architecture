"""A Python module rename without rope: the module's file or package directory moved, every spelling of it in an
import and every name or attribute that Python's scoping resolves to it rewritten, in each file's own text."""

from __future__ import annotations

import ast
import keyword
import sys
from pathlib import Path

from living_architecture.contract import message
from living_architecture.refactor.bindings import BindingCheck, EntryEdits, first_conflict, module_binding
from living_architecture.refactor.diff_render import edit_description, move_description
from living_architecture.refactor.entry_location import Entry, EntryLocator
from living_architecture.refactor.locators import cannot_rename
from living_architecture.refactor.move_edits import NameConflict
from living_architecture.refactor.occurrence_index import candidate_files
from living_architecture.refactor.progress import Progress, Refused, refusal
from living_architecture.refactor.python_source import SourceFile, dotted_segments, nfkc
from living_architecture.refactor.rename_map import changes_of, emit, undecodable
from living_architecture.refactor.rename_union import RenameOptions, Session
from living_architecture.refactor.sites import Keeps, resolve_keeps
from living_architecture.refactor.static_resolver import Module, Value
from living_architecture.refactor.text_edits import TextEdit, merge_edits
from living_architecture.refactor.timings import timed
from living_architecture.refactor.writer import FileMove, FileWrite


class ModuleRename:
    """The rename of `entry`'s module to `new_name`, located by `locator` over `session`'s snapshot."""

    def __init__(self, session: Session, locator: EntryLocator, entry: Entry, new_name: str,
                 options: RenameOptions) -> None:
        self.session = session
        self.snapshot = session.snapshot
        self.locator = locator
        self.entry = entry
        self.new = new_name
        self.options = options
        self.module = entry.module
        self.old = Path(self.module).stem if self.module is not None else entry.name
        self._file = self._module_file()

    def _module_file(self) -> Path | None:
        """The module's own file, a package's `__init__.py`; None for a namespace package or a library module."""
        if self.module is None:
            return None
        path = self.session.root / self.module
        if path.is_dir():
            init = path / "__init__.py"
            return init.resolve() if init.is_file() else None
        return path.resolve()

    def _names(self, dotted: str | None) -> bool:
        """`dotted` names the renamed module (or, for a package, the package)."""
        if dotted is None or self.module is None:
            return False
        found = self.locator.folders(dotted)
        if found is not None:
            return self._file is not None and found[0] == self._file
        rel = dotted.replace(".", "/")
        return any((folder / rel).resolve() == (self.session.root / self.module).resolve()
                   for folder in self.locator.folders.folders)

    def _value_names(self, value: Value) -> bool:
        return value is not None and value[0] == "module" and self._names(value[1])

    # ---- sites

    def _edit(self, rel: str, span: tuple[int, int], text: str | None = None) -> TextEdit:
        return TextEdit(path=rel, start=span[0], end=span[1], new_text=self.new if text is None else text)

    def _file_edits(self, rel: str) -> list[TextEdit]:
        """Every spelling of the module in `rel`'s imports, and every name or attribute resolving to it."""
        module = self.locator.module(rel)
        source = self.snapshot.source(rel)
        if module is None:
            return []
        out: list[TextEdit] = []
        for node in source.nodes:
            if isinstance(node, ast.Import):
                out += self._import(rel, source, node)
            elif isinstance(node, ast.ImportFrom):
                out += self._from_import(rel, source, module, node)
        scopes = self.locator.load_scopes(rel, module)
        for node in source.nodes:
            scope = scopes.get(id(node))
            if scope is None or not isinstance(node, (ast.Name, ast.Attribute)):
                continue
            named = node.id if isinstance(node, ast.Name) else node.attr
            span = source.name_span(node)
            if nfkc(named) == self.old and span is not None and self._value_names(self.locator.resolver.resolve(module, scope, node)):
                out.append(self._edit(rel, span))
        return out + self._all_edits(rel, source, module)

    def _all_edits(self, rel: str, source: SourceFile, module: Module) -> list[TextEdit]:
        """Each `__all__` string the module resolves to the renamed module: a binding of it, or its own submodule."""
        strings = [n for n in source.all_strings() if n.value == self.old]
        if not strings or not self._value_names(self.locator.resolver.member(module.dotted, self.old)):
            return []
        spans = [source.word(*source.span(n), self.old) for n in strings]
        return [self._edit(rel, span, nfkc(self.new)) for span in spans if span is not None]

    def _import(self, rel: str, source: SourceFile, node: ast.Import) -> list[TextEdit]:
        out: list[TextEdit] = []
        for alias in node.names:
            start, end = source.span(alias)  # pyright: ignore[reportArgumentType]
            parts = alias.name.split(".")
            spans = dotted_segments(source.text, start, end)[: len(parts)]
            hits = [i for i in range(len(spans)) if parts[i] == self.old and self._names(".".join(parts[: i + 1]))]
            out += [self._edit(rel, spans[i]) for i in hits]
            if alias.asname == self.old and len(parts) - 1 in hits:
                own = source.name_span(alias)
                out += [self._edit(rel, own)] if own is not None else []
        return out

    def _from_import(self, rel: str, source: SourceFile, module: Module, node: ast.ImportFrom) -> list[TextEdit]:
        absolute = module.binder.from_module(node)
        return self._from_path(rel, source, node, absolute) + self._from_names(rel, source, node, absolute)

    def _from_path(self, rel: str, source: SourceFile, node: ast.ImportFrom, absolute: str | None) -> list[TextEdit]:
        """The renamed segments of the module path of `from … import`."""
        written = node.module.split(".") if node.module else []
        if absolute is None or not written:
            return []
        parts = absolute.split(".")
        spans = source.from_path(node)
        base = len(parts) - len(written)
        return [self._edit(rel, spans[j]) for j in range(len(spans))
                if written[j] == self.old and self._names(".".join(parts[: base + j + 1]))]

    def _from_names(self, rel: str, source: SourceFile, node: ast.ImportFrom, absolute: str | None) -> list[TextEdit]:
        """The imported names of `from … import` that are the module, with an alias spelled like it."""
        if absolute is None and node.level == 0:
            return []
        return [e for alias in node.names if alias.name == self.old for e in self._from_name(rel, source, alias, absolute)]

    def _from_name(self, rel: str, source: SourceFile, alias: ast.alias, absolute: str | None) -> list[TextEdit]:
        full = f"{absolute}.{alias.name}" if absolute else alias.name
        value = self.locator.resolver.member(absolute, alias.name) if absolute else None
        if not (self._value_names(value) or value is None and self._names(full)):
            return []
        span = source.span(alias)  # pyright: ignore[reportArgumentType]
        word = source.word(span[0], span[1], alias.name)
        out = [self._edit(rel, word)] if word is not None else []
        own = source.name_span(alias) if alias.asname == self.old else None
        return out + ([self._edit(rel, own)] if own is not None and own != word else [])

    def _library_edits(self) -> list[TextEdit]:
        """An alias of a library module, `import M as A`, renamed with every name in its file it binds; any other
        library module refuses."""
        rel = self.entry.rel
        module = self.locator.module(rel)
        source = self.snapshot.source(rel)
        if module is None:
            raise cannot_rename()
        dotted = str(self.entry.key[3])
        aliases = [node for scope, bound, node in module.binder.bound
                   if bound == self.old and isinstance(node, ast.alias) and node.asname == self.old
                   and isinstance(source.parent(node), ast.Import) and node.name == dotted]
        if not aliases:
            raise cannot_rename()
        out = [self._edit(rel, span) for a in aliases if (span := source.name_span(a)) is not None]
        scopes = self.locator.load_scopes(rel, module)
        for node in source.of_type(ast.Name):
            scope = scopes.get(id(node))
            if scope is not None and node.id == self.old and self.locator.resolver.resolve(module, scope, node) == ("module", dotted):
                out.append(self._edit(rel, source.span(node)))
        return out

    def edits(self) -> list[TextEdit]:
        """Every edit of the rename, merged."""
        if self.module is None:
            return merge_edits(self._library_edits())
        rels = candidate_files(self.session.python_files(), self.snapshot.text, self.snapshot.source, {self.old})
        return merge_edits([e for rel in rels for e in self._file_edits(rel)])

    def move(self) -> FileMove | None:
        if self.module is None:
            return None
        parent = Path(self.module).parent.as_posix()
        name = nfkc(self.new) if (self.session.root / self.module).is_dir() else nfkc(self.new) + ".py"
        return FileMove(rel=self.module, dest=name if parent == "." else f"{parent}/{name}")

    # ---- checks

    def taken(self) -> NameConflict | None:
        """The finding when the module's package already binds the new name: a module, a package (its `__init__.py`,
        else its first Python file) or a binding of its `__init__.py`."""
        if self.module is None or self.old == nfkc(self.new):
            return None
        rels = self.session.all_python_files()
        parent = Path(self.module).parent.as_posix()
        parent = "" if parent == "." else parent
        base = f"{parent}/{nfkc(self.new)}" if parent else nfkc(self.new)
        if f"{base}.py" in rels:
            return NameConflict(self.new, f"{base}.py", 1)
        inside = sorted(rel for rel in rels if rel.startswith(base + "/"))
        if inside:
            init = f"{base}/__init__.py"
            return NameConflict(self.new, init if init in inside else inside[0], 1)
        init = f"{parent}/__init__.py" if parent else "__init__.py"
        offset = module_binding(self.snapshot.text(init), self.new) if init in rels else None
        return None if offset is None else NameConflict(self.new, init, self.snapshot.source(init).line(offset))

    def stub(self, move: FileMove, text: str, removal: str) -> FileWrite:
        """The stub left at the moved module's old path: `text` with its old and new dotted names and `removal`."""
        old = self.session.modname(move.rel)
        parent = old.rpartition(".")[0]
        new = f"{parent}.{nfkc(self.new)}" if parent else nfkc(self.new)
        filled = text.replace("{old}", old).replace("{new}", new).replace("{removal}", removal)
        return FileWrite(rel=move.rel, old=None, new=filled.encode())

    def moved(self, move: FileMove | None) -> dict[str, str]:
        """Each project file the move moves, to its new path."""
        if move is None:
            return {}
        return {rel: move.dest + rel[len(move.rel):] for rel in self.session.all_python_files()
                if rel == move.rel or rel.startswith(move.rel + "/")}


def run_module_rename(session: Session, locator: EntryLocator, entry: Entry, new_name: str | None,
                      options: RenameOptions, apply_: bool, progress: Progress, *, stub: str | None = None) -> int:
    """A module rename, its `--keep` sites left, with `--stub` the `stub` text left at the old path; refused when the
    new name is taken, its edits change what a name means, or a site matches nothing it must."""
    if new_name is None or not new_name.isidentifier() or keyword.iskeyword(nfkc(new_name)):
        raise cannot_rename()
    rename = ModuleRename(session, locator, entry, new_name, options)
    keeps = Keeps(options.keep, session.root)
    with timed("resolve"):
        found = rename.taken()
    every: list[TextEdit] = []
    written: list[TextEdit] = []
    move: FileMove | None = None
    same = rename.old == nfkc(new_name)
    computed = found is None and not same
    if computed:
        with timed("references"):
            every = rename.edits()
        written = [e for e in every if not keeps.kept(e.path, session.snapshot.source(e.path).line(e.start))]
        move = rename.move()
        if move is not None and keeps.kept(move.rel, None):
            move = None
    olds = [] if same else [rename.old]
    listed = undecodable(session.snapshot, session.all_python_files(), olds, keeps)
    if found is None:
        _resolve_keeps(session, keeps, written)
    if computed:
        progress.phase("conflicts")
        with timed("conflicts"):
            check = BindingCheck(session.python_files(), session.source_folders(), session.snapshot.source)
            found = first_conflict(next(check.conflicts(
                [[EntryEdits(index=1, new_name=new_name, edits=written, kept=[e for e in every if e not in written])]],
                rename.moved(move))), session.snapshot.source)
    if found is not None:
        raise Refused([refusal(message("refactor.name-conflict", name=found.name, path=found.path, line=found.line))])
    for finding in listed:
        print(finding.text, file=sys.stderr)
    _emit(rename, written, move, stub, apply_, progress)
    return 0


def _resolve_keeps(session: Session, keeps: Keeps, written: list[TextEdit]) -> None:
    """Each unneeded whole-path keep's warning printed; `Refused` when a line keep matches no written edit."""
    source = session.snapshot.source
    warnings, unmatched = resolve_keeps(keeps, ((e.path, source(e.path).line(e.start)) for e in written))
    for warning in warnings:
        print(warning, file=sys.stderr)
    if unmatched:
        raise Refused(unmatched)


def _emit(rename: ModuleRename, written: list[TextEdit], move: FileMove | None, stub: str | None, apply_: bool,
          progress: Progress) -> None:
    """The rename's diff, its move and, with `--stub`, the stub at the old path; written with `apply_`."""
    session, removal = rename.session, rename.options.stub
    described, writes = changes_of(session.snapshot, written)
    moves = [move] if move is not None else []
    described += [(m.rel, move_description(m.rel, m.dest)) for m in moves]
    creates = [rename.stub(move, stub, removal)] if move is not None and stub is not None and removal is not None else []
    described += [(c.rel, edit_description(c.rel, "", c.new.decode())) for c in creates]
    header = message("refactor.rename-header", old=rename.old, new=rename.new)
    emit(session.root, [header], described, apply_, writes, moves, progress, creates=creates)
