"""`dr-refactor rename-map`: rename and retarget entries resolved against the code before the map, computed on one
snapshot and one language server, printed as one diff and written all or nothing. `rename` and `retarget` are
one-entry maps."""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rope.base import pynamesdef
from rope.base.change import ChangeContents, ChangeSet, MoveResource
from rope.base.exceptions import BadIdentifierError, RefactoringError
from rope.base.fscommands import unicode_to_file_data
from rope.base.project import Project
from rope.base.pyobjectsdef import PyModule
from rope.base.resources import File
from rope.refactor.rename import Rename

from living_architecture.config import ConfigError
from living_architecture.contract import message
from living_architecture.lang import LanguageServer, LanguageServerError
from living_architecture.refactor.keyed import TypeFacts, UnresolvedBase
from living_architecture.refactor.locators import RefactorError, resolve, resource
from living_architecture.refactor.map_file import MapEntry, MapError
from living_architecture.refactor.outcomes import Finding
from living_architecture.refactor.rename_union import RenameOptions, Session, SymbolRename, _normalize
from living_architecture.refactor.retarget import AliasRetarget
from living_architecture.refactor.sites import Keeps, SiteError
from living_architecture.refactor.symbol_path import LocatorError, declaration_scope, locate
from living_architecture.refactor.text_edits import TextEdit, apply_edits, merge_edits
from living_architecture.refactor.writer import FileMove, FileWrite, apply, verify

_WORD = re.compile(r"\w+")


class MapConflict(Exception):
    """Two entries rewrite one site differently."""

    def __init__(self, path: str, line: int, first: int, second: int) -> None:
        super().__init__(path)
        self.text = message("refactor.map-conflict", path=path, line=line, first=first, second=second)


class Refused(Exception):
    """The refactor refuses; `lines` go to stderr (exit 1)."""

    def __init__(self, lines: list[str]) -> None:
        super().__init__("\n".join(lines))
        self.lines = lines


class _Resolved:
    """An entry located: its file, rope's renamer, its canonical symbol and its intent."""

    def __init__(self, entry: MapEntry, rel: str, renamer: Rename, key: tuple[object, ...]) -> None:
        self.entry = entry
        self.rel = rel
        self.renamer = renamer
        self.key = key
        self.target_key: tuple[object, ...] | None = None
        self.target_name = ""
        self.line = 0

    def intent(self) -> tuple[object, ...]:
        return ("retarget", self.target_key) if self.entry.retarget is not None else ("rename", self.entry.new_name)


def _key(renamer: Rename, rel: str, offset: int) -> tuple[object, ...]:
    """The declaration rope resolves the renamer's name to, else the location."""
    pyname = renamer.old_pyname
    location = pyname.get_definition_location() if pyname is not None else None
    module, line = location or (None, None)
    path = module.get_resource().path if isinstance(module, PyModule) and module.get_resource() is not None else None
    if path is None or line is None:
        return ("site", rel, offset)
    kind = "parameter" if isinstance(pyname, pynamesdef.ParameterName) else "name"
    return (kind, path, line, renamer.get_old_name())


def _raw_offset(raw: str, offset: int) -> int:
    """`offset` in rope's newline-normalized text as an offset in `raw`."""
    count = 0
    index = raw.find("\r\n")
    while index != -1 and index - count < offset:
        count += 1
        index = raw.find("\r\n", index + 2)
    return offset + count


def _definition_line(renamer: Rename) -> tuple[str | None, int | None]:
    location = renamer.old_pyname.get_definition_location() if renamer.old_pyname is not None else None
    module, line = location or (None, None)
    resource_ = module.get_resource() if isinstance(module, PyModule) else None
    return (resource_.path if resource_ is not None else None), line


class RenameMap:
    """The entries of a map computed as one refactor."""

    def __init__(self, project: Project, entries: list[MapEntry], options: RenameOptions, map_shown: str) -> None:
        self.project = project
        self.entries = entries
        self.options = options
        self.map_shown = map_shown
        self.session = Session(project)
        self.root = self.session.root

    # ---- resolution

    def _locate(self, entry: MapEntry) -> tuple[str, int]:
        found = resource(self.project, entry.path)
        offset, _ = resolve(entry.locator, entry.path)
        return found.path, offset

    def _renamer(self, rel: str, offset: int) -> tuple[str, int, Rename]:
        """rope's renamer at `offset`; where rope cannot resolve the name, at the declaration the checker finds."""
        try:
            return rel, offset, Rename(self.project, self.project.get_resource(rel), offset)
        except (RefactoringError, BadIdentifierError):
            raw = self.session.snapshot.text(rel)
            raw_offset = _raw_offset(raw, offset)
            with LanguageServer(self.root, read=self.session.read) as server:
                server.open(self.root / rel, raw)
                found = [s for s in server.definition(self.root / rel, raw_offset) if self.session.rel(s.path)]
            if len(found) != 1 or (found[0].path, found[0].start) == (self.root / rel, raw_offset):
                raise
            target = str(self.session.rel(found[0].path))
            target_offset = found[0].start - self.session.snapshot.text(target).count("\r\n", 0, found[0].start)
            return target, target_offset, Rename(self.project, self.project.get_resource(target), target_offset)

    def _resolve(self, entry: MapEntry) -> _Resolved:
        rel, offset, renamer = self._renamer(*self._locate(entry))
        resolved = _Resolved(entry, rel, renamer, _key(renamer, rel, offset))
        if entry.retarget is not None:
            self._resolve_target(resolved)
        return resolved

    def _resolve_target(self, resolved: _Resolved) -> None:
        entry, rel = resolved.entry, resolved.rel
        source = self.session.snapshot.source(rel)
        alias = entry.locator.symbol or resolved.renamer.get_old_name()
        refused = LocatorError(message("refactor.retarget-scope", target=entry.retarget, alias=alias))
        located = locate(source, str(entry.retarget), entry.file)
        word = _WORD.match(source.text, located.offset)
        def_rel, def_line = _definition_line(resolved.renamer)
        if word is None or def_rel != rel or def_line is None:
            raise refused
        resolved.target_name = word.group()
        resolved.line = def_line
        alias_scope = declaration_scope(source, resolved.renamer.get_old_name(), def_line)
        target_scope = declaration_scope(source, resolved.target_name, source.line(located.offset))
        if alias_scope is None or target_scope is None or alias_scope[0] is not target_scope[0]:
            raise refused
        if isinstance(target_scope[1], ast.alias):
            raise refused
        target = Rename(self.project, self.project.get_resource(rel), located.offset - source.text.count("\r\n", 0, located.offset))
        resolved.target_key = _key(target, rel, located.offset)

    def resolve(self) -> list[_Resolved]:
        """Every entry located before any is computed; duplicates merged or refused."""
        out: list[_Resolved] = []
        for entry in self.entries:
            resolved = self._resolve(entry)
            first = next((r for r in out if r.key == resolved.key), None)
            if first is None:
                out.append(resolved)
            elif first.intent() != resolved.intent():
                raise MapError(message("refactor.map-duplicate", map=self.map_shown, first=first.entry.index,
                                       second=entry.index))
        return out

    # ---- computing

    def build(self, resolved: list[_Resolved]) -> list[SymbolRename]:
        finals = {r.key: r.entry.new_name for r in resolved if r.entry.new_name is not None}
        renames: list[SymbolRename] = []
        for r in resolved:
            if r.entry.retarget is not None:
                target = finals.get(r.target_key) or r.target_name  # pyright: ignore[reportArgumentType]
                renames.append(AliasRetarget(self.session, r.renamer, target, self.options, line=r.line))
            else:
                renames.append(SymbolRename(self.session, r.renamer, str(r.entry.new_name), self.options))
        return renames

    def compute(self, renames: list[SymbolRename]) -> None:
        active = [r for r in renames if r.new != r.old]
        for r in active:
            r.prepare()
        self._check_sites(active)
        candidates = sorted({rel for r in active for rel in r.candidates})
        with LanguageServer(self.root, read=self.session.read) as server:
            for rel in candidates:
                server.open(self.root / rel, self.session.snapshot.text(rel))
            facts = TypeFacts(server, self.session.load)
            for r in active:
                r.seed(facts)
            renamed = {site for r in active for site in r.seeds}
            for r in active:
                r.is_renamed = renamed.__contains__
            for r in active:
                r.rules(server, facts)
        olds = {r.old for r in active}
        for r in active:
            r.renamed_names = olds
            r.finish()
            r.edits = merge_edits(r.edits)
            if isinstance(r, AliasRetarget):
                r.retarget()

    def _check_sites(self, renames: list[SymbolRename]) -> None:
        """`SiteError` for the first `--with` or `--without` site no member entry's stand-ins hold."""
        matched = {raw for r in renames if r.member for raw in r.matched_sites}
        for raw in (*self.options.with_sites, *self.options.without_sites):
            if raw not in matched:
                raise SiteError("refactor.not-stand-in", raw)

    def keep(self, renames: list[SymbolRename]) -> None:
        """Drop every edit, blind spot and leftover at a kept site; `SiteError` for a keep that matched nothing."""
        keeps = Keeps(self.options.keep, self.root)
        snapshot = self.session.snapshot
        for r in renames:
            r.edits = [e for e in r.edits if not keeps.kept(e.path, snapshot.source(e.path).line(e.start))]
            r.blindspots = [b for b in r.blindspots if not keeps.kept(b.path, b.line)]
            r.leftovers = [f for f in r.leftovers if not keeps.kept(f.path, f.line, mark=False)]
        keeps.check()

    def merged(self, renames: list[SymbolRename], indexes: list[int]) -> list[TextEdit]:
        """Every entry's edits; identical ones merged, differing ones on one span a `MapConflict`."""
        tagged = sorted(
            {(e, i) for r, i in zip(renames, indexes, strict=True) for e in r.edits},
            key=lambda t: (t[0].path, t[0].start, t[0].end, t[1]),
        )
        out: list[TextEdit] = []
        owner: list[int] = []
        for edit, index in tagged:
            if out and out[-1] == edit:
                continue
            if out and out[-1].path == edit.path and edit.start < out[-1].end:
                line = self.session.snapshot.source(edit.path).line(edit.start)
                raise MapConflict(edit.path, line, *sorted((owner[-1], index)))
            out.append(edit)
            owner.append(index)
        return out

    def refusal(self, renames: list[SymbolRename]) -> list[str]:
        """The lines refusing the map, or none when it may proceed."""
        refusals = sorted((f for r in renames if isinstance(r, AliasRetarget) for f in r.refusals),
                          key=lambda f: (f.path, f.line, f.col))
        if refusals:
            return [f.text for f in refusals]
        blindspots = sorted((b for r in renames for b in r.blindspots), key=lambda f: (f.path, f.line, f.col))
        stand_ins = sorted((s for r in renames for s in r.stand_in_findings()), key=lambda f: (f.path, f.line, f.col))
        blind = [] if self.options.allow_blindspots else blindspots
        if not blind and not stand_ins:
            return []
        attrs = ", .".join(dict.fromkeys(r.old for r in renames if r.blindspots))
        closing = [message("refactor.blindspots", count=len(blind), attr=attrs)] if blind else []
        return [*(f.text for f in blindspots), *(f.text for f in stand_ins), *closing]

    def findings(self, renames: list[SymbolRename]) -> list[Finding]:
        """The blind spots let through and the leftovers, each group sorted."""
        blindspots = sorted((b for r in renames for b in r.blindspots), key=lambda f: (f.path, f.line, f.col))
        leftovers = sorted({f for r in renames for f in r.leftovers}, key=lambda f: (f.path, f.line, f.col, f.text))
        return [*blindspots, *leftovers]

    def check_conflicts(self, renames: list[SymbolRename]) -> None:
        for r in renames:
            r.check_conflicts(r.edits)

    def outputs(self, edits: list[TextEdit]) -> tuple[ChangeSet, list[FileWrite]]:
        """The change set to print and the writes."""
        snapshot = self.session.snapshot
        changes = ChangeSet("")
        writes: list[FileWrite] = []
        for rel in sorted({e.path for e in edits}):
            raw = snapshot.text(rel)
            text = apply_edits(raw, [e for e in edits if e.path == rel])
            if text == raw:
                continue
            changes.add_change(ChangeContents(self.project.get_resource(rel), _normalize(text), old_contents=_normalize(raw)))
            writes.append(FileWrite(rel=rel, old=snapshot.data(rel), new=snapshot.encode(rel, text)))
        return changes, writes


def change_set_writes(project: Project, changes: ChangeSet) -> tuple[list[FileWrite], list[FileMove]]:
    """A rope change set as writes and moves."""
    root = Path(project.address).resolve()
    writes: list[FileWrite] = []
    moves: list[FileMove] = []
    for change in changes.changes:
        if isinstance(change, ChangeContents):
            file: File = change.resource
            file.read()
            data = unicode_to_file_data(change.new_contents, newlines=file.newlines)
            writes.append(FileWrite(rel=file.path, old=(root / file.path).read_bytes(), new=bytes(data)))
        elif isinstance(change, MoveResource):
            moves.append(FileMove(rel=change.resource.path, dest=change.new_resource.path))
    return writes, moves


def emit(project: Project, headers: list[str], changes: ChangeSet, apply_: bool, writes: list[FileWrite],
         moves: list[FileMove]) -> None:
    """Print the headers and the changes sorted by path, then write them with `--apply`."""
    ordered = sorted(changes.changes, key=lambda c: c.resource.path)
    print("\n".join(headers) + "\n\n\n" + "".join(c.get_description() + "\n" for c in ordered))
    touched = [c.resource.path for c in ordered]
    if apply_:
        apply(Path(project.address).resolve(), writes, moves)
        print(message("refactor.applied", count=len(touched)))
        for p in touched:
            print(message("refactor.applied-file", path=p))
    else:
        print(message("refactor.dry-run", count=len(touched)))


def run_map(project: Project, entries: list[MapEntry], options: RenameOptions, *, apply_: bool, map_shown: str,
            module_rename: Callable[[_Resolved], int]) -> int:
    """0 when computed (and written with `--apply`); `Refused` lines and exit 1 when it refuses."""
    engine = RenameMap(project, entries, options, map_shown)
    try:
        resolved = engine.resolve()
        modules = [r for r in resolved if r.renamer._is_renaming_a_module()]  # pyright: ignore[reportPrivateUsage]
        if modules:
            if len(resolved) > 1:
                raise RefactorError(message("refactor.cannot-rename"))
            return module_rename(modules[0])
        renames = engine.build(resolved)
        engine.compute(renames)
    except (RefactoringError, BadIdentifierError):
        raise RefactorError(message("refactor.cannot-rename")) from None
    except LanguageServerError:
        raise RefactorError(message("refactor.pyright-failed")) from None
    except ConfigError as exc:
        raise RefactorError(str(exc)) from None
    except UnresolvedBase as base:
        root = engine.root
        path = (base.path.relative_to(root) if base.path.is_relative_to(root) else base.path).as_posix()
        raise RefactorError(message("refactor.unresolved-base", name=base.name, path=path, line=base.line)) from None
    engine.keep(renames)
    engine.check_conflicts(renames)
    edits = engine.merged(renames, [r.entry.index for r in resolved])
    refusal = engine.refusal(renames)
    if refusal:
        raise Refused(refusal)
    if options.unsure:
        print(message("refactor.unsure-warning"))
    for finding in engine.findings(renames):
        print(finding.text, file=sys.stderr)
    changes, writes = engine.outputs(edits)
    if apply_:
        verify(engine.root, writes)
    emit(project, [r.header() for r in renames], changes, apply_, writes, [])
    return 0


def entry_options(options: dict[str, Any]) -> RenameOptions:
    return RenameOptions(
        in_hierarchy=bool(options.get("in_hierarchy", True)),
        unsure=options.get("unsure") == "include",
        allow_blindspots=bool(options.get("allow_blindspots")),
        with_sites=tuple(options.get("with_stand_ins") or ()),
        without_sites=tuple(options.get("without_stand_ins") or ()),
        keep=tuple(options.get("keep") or ()),
        docs=bool(options.get("docs")),
    )
