"""A Python module rename without rope, as one entry of a rename map: the module's file or package directory moved, every
spelling of it in an import and every name or attribute that Python's scoping resolves to it rewritten, in each file's
own text."""

from __future__ import annotations

import ast
import keyword
from collections.abc import Callable, Iterable
from pathlib import Path

from typing_extensions import override

from living_architecture.contract import message
from living_architecture.refactor.bindings import Conflict, bindings_after, module_binding
from living_architecture.refactor.entry_location import Entry, EntryLocator
from living_architecture.refactor.keyed import TypeFacts
from living_architecture.refactor.locators import cannot_rename
from living_architecture.refactor.move_edits import NameConflict
from living_architecture.refactor.occurrence_index import RunIndex, candidate_files
from living_architecture.refactor.outcomes import Finding
from living_architecture.refactor.python_source import SourceFile, dotted_segments, nfkc
from living_architecture.refactor.rename_union import MapRename, RenameOptions, RenameResult, Session
from living_architecture.refactor.static_resolver import Module, Value
from living_architecture.refactor.text_edits import TextEdit, merge_edits
from living_architecture.refactor.timings import timed
from living_architecture.refactor.writer import FileMove, FileWrite

_INIT = "__init__.py"


def valid_module_name(name: str) -> bool:
    """`name` can name a Python module: an identifier, no keyword."""
    return name.isidentifier() and not keyword.iskeyword(nfkc(name))


def _init_of(folder: str) -> str:
    """The `__init__.py` of `folder` (`""` or `"."` for the root)."""
    return f"{folder}/{_INIT}" if folder not in ("", ".") else _INIT


class ModuleResult(RenameResult):
    """A module rename's result: also its module, its move, whether it is a package, whether its new name is its own,
    and the file a finding about it names."""

    module: str | None
    move: FileMove | None
    package: bool
    same: bool
    site: str | None

    @override
    def live(self) -> bool:
        return super().live() and not self.same

    def stub(self, session: Session, text: str, removal: str) -> FileWrite | None:
        """The stub left at the moved module's old path: `text` with its old and new dotted names and `removal`."""
        if self.move is None:
            return None
        old = session.modname(self.move.rel)
        parent = old.rpartition(".")[0]
        new = f"{parent}.{nfkc(self.new)}" if parent else nfkc(self.new)
        filled = text.replace("{old}", old).replace("{new}", new).replace("{removal}", removal)
        return FileWrite(rel=self.move.rel, old=None, new=filled.encode())


def _is_self(root: Path, rel: str, other: str) -> bool:
    """`other` is `rel` itself on disk, spelled in another case at most."""
    return other.lower() == rel.lower() and (root / other).samefile(root / rel)


class ModuleRename(MapRename):
    """The rename of `entry`'s module to `new_name`, located by `locator` over `session`'s snapshot: `prepare` finds
    its edits and its move."""

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
        self.edits: list[TextEdit] = []
        self.move: FileMove | None = None
        self.seeds: set[tuple[str, int]] = set()
        self.is_renamed: Callable[[tuple[str, int]], bool] = lambda _site: False
        self.matched_sites: set[str] = set()
        self.member = False
        self.renamed_names: set[str] = {self.old}
        self.blindspots: list[Finding] = []
        self.leftovers: list[Finding] = []
        self.unverified: list[tuple[Finding, TextEdit]] = []
        self._file = self._module_file()

    @property
    def same(self) -> bool:
        """The new name is the module's own, as Python reads it."""
        return self.old == nfkc(self.new)

    def package(self) -> bool:
        return self.module is not None and (self.session.root / self.module).is_dir()

    def stubbable(self) -> bool:
        """A module file: not a package, a namespace package or a library module's alias."""
        return self.module is not None and not self.package()

    def _module_file(self) -> Path | None:
        """The module's own file, a package's `__init__.py`; None for a namespace package or a library module."""
        if self.module is None:
            return None
        path = self.session.root / self.module
        if path.is_dir():
            init = path / _INIT
            return init.resolve() if init.is_file() else None
        return path.resolve()

    def site_file(self) -> str:
        """The file a finding about the module names: its own, a package's `__init__.py`, else its first Python file."""
        assert self.module is not None
        if not self.package():
            return self.module
        inside = sorted(rel for rel in self.session.all_python_files() if rel.startswith(self.module + "/"))
        init = _init_of(self.module)
        return init if init in inside or not inside else inside[0]

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

    def _edits(self) -> list[TextEdit]:
        """Every edit of the rename, merged."""
        if self.module is None:
            return merge_edits(self._library_edits())
        rels = candidate_files(self.session.python_files(), self.snapshot.text, self.snapshot.source, {self.old})
        return merge_edits([e for rel in rels for e in self._file_edits(rel)])

    def _move(self) -> FileMove | None:
        """The module's file or package directory renamed beside itself."""
        if self.module is None:
            return None
        parent = Path(self.module).parent.as_posix()
        name = nfkc(self.new) if self.package() else nfkc(self.new) + ".py"
        return FileMove(rel=self.module, dest=name if parent == "." else f"{parent}/{name}")

    # ---- checks

    def taken(self) -> NameConflict | None:
        """The finding when the module's package already binds the new name: a module, a package (its `__init__.py`,
        else its first Python file) or a binding of its `__init__.py`."""
        if self.module is None or self.same:
            return None
        rels = self.session.all_python_files()
        root = self.session.root
        parent = Path(self.module).parent.as_posix()
        parent = "" if parent == "." else parent
        base = f"{parent}/{nfkc(self.new)}" if parent else nfkc(self.new)
        file = f"{base}.py"
        if file in rels or ((root / file).is_file() and not _is_self(root, self.module, file)):
            return NameConflict(self.new, file, 1)
        inside = sorted(rel for rel in rels if rel.startswith(base + "/"))
        if not inside and (root / base).is_dir() and not _is_self(root, self.module, base):
            spelled = (base + rel[len(base):] for rel in rels if rel.lower().startswith(base.lower() + "/"))
            inside = sorted(rel for rel in spelled if (root / rel).is_file())
        if inside:
            init = _init_of(base)
            return NameConflict(self.new, init if init in inside else inside[0], 1)
        init = _init_of(parent)
        offset = module_binding(self.snapshot.text(init), self.new) if init in rels else None
        return None if offset is None else NameConflict(self.new, init, self.snapshot.source(init).line(offset))

    # ---- the map's phases

    @override
    def header(self) -> str:
        return message("refactor.rename-header", old=self.old, new=self.new)

    @override
    def stand_in_findings(self) -> list[Finding]:
        return []

    @override
    def prepare(self, index: RunIndex) -> None:
        """The edits and the move."""
        if self.same:
            return
        with timed("references"):
            self.edits = self._edits()
            self.move = self._move()

    @override
    def seed(self, facts: TypeFacts) -> None:
        return None

    @override
    def rules(self, index: RunIndex, facts: TypeFacts) -> None:
        return None

    @override
    def finish(self) -> None:
        return None

    @override
    def result(self, entry: int, target: str | None, kept: list[TextEdit]) -> ModuleResult:
        return ModuleResult(
            entry=entry, old=self.old, new=self.new, header=self.header(), target=target, member=False,
            check_names=False, edits=self.edits, kept=kept, blindspots=self.blindspots, module=self.module,
            move=self.move, package=self.package(), same=self.same,
            site=self.site_file() if self.module is not None else None,
        )


def innermost_first(moves: Iterable[FileMove]) -> list[FileMove]:
    """`moves` in the order they are made: deepest first, so each is made before any move of a directory holding it."""
    return sorted(moves, key=lambda m: (-len(Path(m.rel).parts), m.rel))


def final_path(rel: str, moves: list[FileMove]) -> str:
    """Where `rel` ends once every one of `moves` (innermost first) is made."""
    for move in moves:
        if rel == move.rel or rel.startswith(move.rel + "/"):
            rel = move.dest + rel[len(move.rel):]
    return rel


def final_paths(files: Iterable[str], moves: Iterable[FileMove]) -> dict[str, str]:
    """Each of `files` that `moves` move, to the path every move holding it composes to."""
    ordered = innermost_first(moves)
    return {rel: dest for rel in files if (dest := final_path(rel, ordered)) != rel}


def move_conflicts(renames: list[ModuleResult], edits: list[TextEdit], source: Callable[[str], SourceFile],
                   files: list[str]) -> list[Conflict]:
    """Two moves ending at one module, each named at the earlier entry's module; and a moved module meeting a binding
    of its new name that the edits give its package's `__init__.py`."""
    moving = [r for r in renames if r.move is not None and r.module is not None]
    ordered = innermost_first(r.move for r in moving if r.move is not None)
    out: list[Conflict] = []
    seen: dict[str, ModuleResult] = {}
    for r in moving:
        assert r.module is not None
        final = final_path(r.module, ordered)
        first = seen.setdefault(final if r.package else final.removesuffix(".py"), r)
        if first is not r and first.site is not None:
            out.append(Conflict(site=(first.site, 0), name=first.new))
    for r in moving:
        assert r.module is not None
        init = _init_of(Path(r.module).parent.as_posix())
        changed = [e for e in edits if e.path == init]
        if init not in files or not changed:
            continue
        own = {e.start for e in r.edits if e.path == init}
        out += [Conflict(site=(init, offset), name=r.new)
                for offset in bindings_after(source(init).text, changed, nfkc(r.new)) if offset not in own]
    return out
