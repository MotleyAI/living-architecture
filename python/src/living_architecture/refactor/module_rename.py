"""A Python module rename without rope: the module's file or package directory moved, every spelling of it in an
import and every name or attribute that Python's scoping resolves to it rewritten, in each file's own text."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

from living_architecture.contract import message
from living_architecture.refactor.bindings import BindingCheck, EntryEdits, first_conflict, module_binding
from living_architecture.refactor.diff_render import move_description
from living_architecture.refactor.entry_location import Entry, EntryLocator
from living_architecture.refactor.locators import RefactorError
from living_architecture.refactor.move_edits import NameConflict
from living_architecture.refactor.occurrence_index import candidate_files
from living_architecture.refactor.progress import Progress, Refusal, Refused, refusal
from living_architecture.refactor.python_source import SourceFile, nfkc
from living_architecture.refactor.rename_map import changes_of, emit, undecodable
from living_architecture.refactor.rename_union import RenameOptions, Session
from living_architecture.refactor.sites import Keeps
from living_architecture.refactor.static_resolver import Module, Value
from living_architecture.refactor.text_edits import TextEdit, merge_edits
from living_architecture.refactor.timings import timed
from living_architecture.refactor.writer import FileMove

_SEGMENT = re.compile(r"(?:\.|[^\S\r\n]|\\\r?\n|\\\r)*([^\W\d]\w*)")


def _segments(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """The spans of the dotted name's identifiers written in `text[start:end]`, in order."""
    out: list[tuple[int, int]] = []
    at = start
    while at < end:
        m = _SEGMENT.match(text, at)
        if m is None or m.start(1) >= end:
            break
        out.append(m.span(1))
        at = m.end()
        if at < end and text[at] not in ". \t\\":
            break
    return out


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

    def _edit(self, rel: str, span: tuple[int, int]) -> TextEdit:
        return TextEdit(path=rel, start=span[0], end=span[1], new_text=self.new)

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
        return out

    def _import(self, rel: str, source: SourceFile, node: ast.Import) -> list[TextEdit]:
        out: list[TextEdit] = []
        for alias in node.names:
            start, end = source.span(alias)  # pyright: ignore[reportArgumentType]
            parts = alias.name.split(".")
            spans = _segments(source.text, start, end)[: len(parts)]
            hits = [i for i in range(len(spans)) if parts[i] == self.old and self._names(".".join(parts[: i + 1]))]
            out += [self._edit(rel, spans[i]) for i in hits]
            if alias.asname == self.old and len(parts) - 1 in hits:
                own = source.name_span(alias)
                out += [self._edit(rel, own)] if own is not None else []
        return out

    def _from_import(self, rel: str, source: SourceFile, module: Module, node: ast.ImportFrom) -> list[TextEdit]:
        out: list[TextEdit] = []
        absolute = module.binder.from_module(node)
        written = (node.module or "").split(".") if node.module else []
        if absolute is not None and written:
            parts = absolute.split(".")
            first = source.offset(node.lineno, node.col_offset)
            keyword = re.compile(r"from\s*\.*\s*").match(source.text, first)
            spans = _segments(source.text, keyword.end() if keyword else first, source.span(node)[1])[: len(written)]
            base = len(parts) - len(written)
            out += [self._edit(rel, spans[j]) for j in range(len(spans))
                    if written[j] == self.old and self._names(".".join(parts[: base + j + 1]))]
        for alias in node.names:
            if alias.name != self.old or absolute is None and node.level == 0:
                continue
            full = f"{absolute}.{alias.name}" if absolute else alias.name
            value = self.locator.resolver.member(absolute, alias.name) if absolute else None
            if not (self._value_names(value) or value is None and self._names(full)):
                continue
            span = source.span(alias)  # pyright: ignore[reportArgumentType]
            word = source.word(span[0], span[1], alias.name)
            out += [self._edit(rel, word)] if word is not None else []
            if alias.asname == self.old:
                own = source.name_span(alias)
                out += [self._edit(rel, own)] if own is not None and own != word else []
        return out

    def _library_edits(self) -> list[TextEdit]:
        """An alias of a library module, `import M as A`, renamed with every name in its file it binds; any other
        library module refuses."""
        rel = self.entry.rel
        module = self.locator.module(rel)
        source = self.snapshot.source(rel)
        if module is None:
            raise RefactorError(message("refactor.cannot-rename"))
        dotted = str(self.entry.key[3])
        aliases = [node for scope, bound, node in module.binder.bound
                   if bound == self.old and isinstance(node, ast.alias) and node.asname == self.old
                   and isinstance(source.parent(node), ast.Import) and node.name == dotted]
        if not aliases:
            raise RefactorError(message("refactor.cannot-rename"))
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
        name = self.new if (self.session.root / self.module).is_dir() else self.new + ".py"
        return FileMove(rel=self.module, dest=name if parent == "." else f"{parent}/{name}")

    # ---- checks

    def taken(self) -> NameConflict | None:
        """The finding when the module's package already binds the new name: a module, a package (its `__init__.py`,
        else its first Python file) or a binding of its `__init__.py`."""
        if self.module is None or self.old == self.new:
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

    def moved(self, move: FileMove | None) -> dict[str, str]:
        """Each project file the move moves, to its new path."""
        if move is None:
            return {}
        return {rel: move.dest + rel[len(move.rel):] for rel in self.session.all_python_files()
                if rel == move.rel or rel.startswith(move.rel + "/")}


def run_module_rename(session: Session, locator: EntryLocator, entry: Entry, new_name: str | None,
                      options: RenameOptions, apply_: bool, progress: Progress) -> int:
    """A module rename, its `--keep` sites left; refused when the new name is taken, its edits change what a name
    means, or a site matches nothing it must."""
    if new_name is None:
        raise RefactorError(message("refactor.cannot-rename"))
    rename = ModuleRename(session, locator, entry, new_name, options)
    keeps = Keeps(options.keep, session.root)
    with timed("resolve"):
        found = rename.taken()
    written: list[TextEdit] = []
    move: FileMove | None = None
    unmatched: list[str] = []
    if found is None and rename.old != new_name:
        with timed("references"):
            every = rename.edits()
        written = [e for e in every if not keeps.kept(e.path, session.snapshot.source(e.path).line(e.start))]
        move = rename.move()
        if move is not None and keeps.kept(move.rel, None):
            move = None
        unmatched = keeps.unmatched()
        progress.phase("conflicts")
        with timed("conflicts"):
            check = BindingCheck(session.python_files(), session.source_folders(), session.snapshot.source)
            found = first_conflict(check.conflicts(
                [EntryEdits(index=1, new_name=new_name, edits=written, kept=[e for e in every if e not in written])],
                rename.moved(move)), session.snapshot.source)
    refusals: list[Refusal] = []
    if found is not None:
        refusals.append(refusal(message("refactor.name-conflict", name=found.name, path=found.path, line=found.line)))
    refusals += [refusal(message("refactor.not-stand-in", site=raw), 2) for raw in (*options.with_sites, *options.without_sites)]
    refusals += [refusal(message("refactor.keep-unmatched", site=raw), 2) for raw in unmatched]
    if refusals:
        raise Refused(refusals)
    for finding in undecodable(session.snapshot, session.all_python_files(), [rename.old], keeps):
        print(finding.text, file=sys.stderr)
    described, writes = changes_of(session.snapshot, written)
    moves = [move] if move is not None else []
    described += [(m.rel, move_description(m.rel, m.dest)) for m in moves]
    header = message("refactor.rename-header", old=rename.old, new=new_name)
    emit(session.root, [header], described, apply_, writes, moves, progress)
    return 0
