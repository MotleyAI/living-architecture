"""`dr-refactor rename-map`: rename and retarget entries resolved against the code before the map, computed on one
snapshot and one language server, printed as one diff and written all or nothing. `rename` and `retarget` are
one-entry maps."""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Callable, Iterable
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
from living_architecture.refactor.baseline_align import align
from living_architecture.refactor.bindings import BindingCheck, EntryEdits, first_conflict
from living_architecture.refactor.keyed import TypeFacts, UnresolvedBase
from living_architecture.refactor.literal_rename import LiteralRename, check_value, literal_member_at
from living_architecture.refactor.locators import RefactorError, resolve, resource
from living_architecture.refactor.map_file import MapEntry, MapError
from living_architecture.refactor.member_namespace import Hierarchy, MemberCheck, RenamedMember
from living_architecture.refactor.outcomes import Finding
from living_architecture.refactor.position_map import Edit
from living_architecture.refactor.python_source import SourceFile
from living_architecture.refactor.rename_union import RenameOptions, Session, SymbolRename, _normalize
from living_architecture.refactor.retarget import (
    AliasRetarget,
    TargetHome,
    attribute_definition,
    definition,
    imported_module,
    module_name,
)
from living_architecture.refactor.retarget_imports import plan_imports
from living_architecture.refactor.routing import language_files
from living_architecture.refactor.sites import Keeps, SiteError
from living_architecture.refactor.symbol_path import LocatorError, declaration_scope, locate
from living_architecture.refactor.text_edits import TextEdit, apply_edits, merge_edits
from living_architecture.refactor.writer import FileChanged, FileMove, FileWrite, apply, verify

_WORD = re.compile(r"\w+")
_CANNOT_RENAME = "refactor.cannot-rename"


Renaming = SymbolRename | LiteralRename


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

    def __init__(self, entry: MapEntry, rel: str, renamer: Rename | None, key: tuple[object, ...],
                 literal: ast.Constant | None = None, offset: int = 0) -> None:
        self.entry = entry
        self.rel = rel
        self.renamer = renamer
        self.key = key
        self.literal = literal
        self.offset = offset
        self.target_key: tuple[object, ...] | None = None
        self.target_name = ""
        self.line = 0
        self.home: TargetHome | None = None
        self.own: tuple[str, int] | None = None

    def intent(self) -> tuple[object, ...]:
        return ("retarget", self.target_key) if self.entry.retarget is not None else ("rename", self.entry.new_name)


def _key(renamer: Rename, rel: str, offset: int) -> tuple[object, ...]:
    """The declaration rope resolves the renamer's name to, else the location."""
    pyname = renamer.old_pyname
    location = pyname.get_definition_location() if pyname is not None else None
    module, line = location or (None, None)
    path = module.get_resource().path if isinstance(module, PyModule) and module.get_resource() is not None else None
    if path is None or line is None:
        return ("site", rel, offset, None)
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


def _unique(findings: Iterable[Finding]) -> list[Finding]:
    """`findings` in path, line and column order, each once: entries sharing an old name scan its sites once."""
    return sorted({(f.path, f.line, f.col, f.text): f for f in findings}.values(), key=lambda f: (f.path, f.line, f.col))


def _import_of(source: SourceFile, alias: ast.AST) -> ast.ImportFrom | None:
    """The `from ... import` statement holding `alias`."""
    assert source.tree is not None
    return next((s for s in ast.walk(source.tree) if isinstance(s, ast.ImportFrom) and any(a is alias for a in s.names)), None)


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

    def _literal(self, entry: MapEntry, rel: str, offset: int) -> _Resolved | None:
        """The entry as a `Literal` member rename, when its locator names a string of a `Literal[...]`."""
        source = self.session.snapshot.source(rel)
        node = literal_member_at(source, _raw_offset(source.text, offset))
        if node is None:
            return None
        if entry.new_name is None:
            raise RefactorError(message(_CANNOT_RENAME))
        check_value(entry.new_name)
        return _Resolved(entry, rel, None, ("literal", rel, source.span(node)[0]), literal=node)

    def _resolve(self, entry: MapEntry) -> _Resolved:
        located = self._locate(entry)
        literal = self._literal(entry, *located)
        if literal is not None:
            return literal
        rel, offset, renamer = self._renamer(*located)
        resolved = _Resolved(entry, rel, renamer, _key(renamer, rel, offset), offset=offset)
        if entry.retarget is not None:
            self._resolve_target(resolved)
        return resolved

    def _resolve_target(self, resolved: _Resolved) -> None:
        """The target beside the alias: declared or imported in the alias's class or module, or the name a re-export
        declaring the alias imports; LocatorError otherwise."""
        entry, rel, renamer = resolved.entry, resolved.rel, resolved.renamer
        assert renamer is not None
        source = self.session.snapshot.source(rel)
        alias = entry.locator.symbol or renamer.get_old_name()
        refused = LocatorError(message("refactor.retarget-scope", target=entry.retarget, alias=alias))
        old = renamer.get_old_name()
        alias_line = source.line(_raw_offset(source.text, resolved.offset))
        alias_scope = declaration_scope(source, old, alias_line)
        if alias_scope is not None and isinstance(alias_scope[1], ast.alias):
            self._reexport_target(resolved, source, alias_scope, alias_line, refused)
            return
        try:
            located = locate(source, str(entry.retarget), entry.file)
        except LocatorError:
            raise refused from None
        word = _WORD.match(source.text, located.offset)
        def_rel, def_line = _definition_line(renamer)
        if word is None or def_rel != rel or def_line is None:
            raise refused
        resolved.target_name = word.group()
        resolved.line = def_line
        alias_scope = declaration_scope(source, old, def_line)
        target_scope = declaration_scope(source, resolved.target_name, source.line(located.offset))
        if alias_scope is None or target_scope is None or alias_scope[0] is not target_scope[0]:
            raise refused
        imported = isinstance(target_scope[1], ast.alias)
        if imported and not isinstance(alias_scope[0], ast.Module):
            raise refused
        target = Rename(self.project, self.project.get_resource(rel), located.offset - source.text.count("\r\n", 0, located.offset))
        resolved.target_key = _key(target, rel, located.offset)
        if not isinstance(alias_scope[0], ast.Module):
            return
        found = definition(target.old_pyname)
        if imported:
            stmt = _import_of(source, target_scope[1])
            if stmt is None:
                raise refused
            exported = target_scope[1].name  # pyright: ignore[reportAttributeAccessIssue]
            module = imported_module(self.session, rel, stmt)
        else:
            exported, module = resolved.target_name, module_name(self.session, rel)
        resolved.home = TargetHome(module=module, exported=exported, local=resolved.target_name, definition=found)

    def _reexport_target(self, resolved: _Resolved, source: SourceFile, alias_scope: tuple[ast.AST, ast.AST], line: int,
                         refused: LocatorError) -> None:
        """The alias declared by `from M import T as ALIAS` at module level: TARGET is `T` from `M`."""
        node = alias_scope[1]
        stmt = _import_of(source, node)
        assert isinstance(node, ast.alias)
        if stmt is None or not isinstance(alias_scope[0], ast.Module) or node.name != resolved.entry.retarget:
            raise refused
        module = imported_module(self.session, resolved.rel, stmt)
        found = attribute_definition(self.project, module, node.name)
        resolved.target_name = node.name
        resolved.line = line
        resolved.own = (resolved.rel, source.offset(node.lineno, node.col_offset) + source.text[
            source.offset(node.lineno, node.col_offset):].index(str(node.asname)))
        resolved.target_key = ("name", found[0], found[1], node.name) if found is not None else ("site", resolved.rel, line, node.name)
        resolved.home = TargetHome(module=module, exported=node.name, local=node.name, definition=found)

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

    def build(self, resolved: list[_Resolved]) -> list[Renaming]:
        finals = {r.key: r.entry.new_name for r in resolved if r.entry.new_name is not None}
        renames: list[Renaming] = []
        for r in resolved:
            if r.literal is not None:
                renames.append(LiteralRename(self.session, r.rel, r.literal, str(r.entry.new_name), self.options))
            elif r.renamer is None:
                raise RefactorError(message(_CANNOT_RENAME))
            elif r.entry.retarget is not None:
                final = finals.get(r.target_key)  # pyright: ignore[reportArgumentType]
                target = final or r.target_name
                home = r.home
                if home is not None and final is not None:
                    home = home.model_copy(update={
                        "exported": final if home.exported == r.target_name else home.exported,
                        "local": final if home.local == r.target_name else home.local})
                renames.append(AliasRetarget(self.session, r.renamer, target, self.options, line=r.line, home=home,
                                             own=r.own, original=r.target_name, entry=r.entry.index))
            else:
                renames.append(SymbolRename(self.session, r.renamer, str(r.entry.new_name), self.options))
        return renames

    def compute(self, renames: list[Renaming]) -> None:
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

    def _check_sites(self, renames: list[Renaming]) -> None:
        """`SiteError` for the first `--with` or `--without` site no member entry's stand-ins hold."""
        matched = {raw for r in renames if r.member for raw in r.matched_sites}
        for raw in (*self.options.with_sites, *self.options.without_sites):
            if raw not in matched:
                raise SiteError("refactor.not-stand-in", raw)

    def retarget(self, renames: list[Renaming], keeps: Keeps) -> None:
        """Each retarget's sites decided with its kept lines, then the imports they need planned once."""
        retargets = [r for r in renames if isinstance(r, AliasRetarget)]
        for r in retargets:
            r.retarget(keeps.kept)
        by_entry = {r.entry: r for r in retargets}
        for entry, edit in plan_imports(self.session, [n for r in retargets for n in r.needs]):
            by_entry[entry].imports.append(edit)
        for r in retargets:
            r.edits += r.imports

    def keep(self, renames: list[Renaming], keeps: Keeps) -> list[list[TextEdit]]:
        """Drop every edit, blind spot and leftover at a kept site (a retarget's are dropped already); each rename's
        dropped edits. `SiteError` for a keep that matched nothing."""
        snapshot = self.session.snapshot
        dropped: list[list[TextEdit]] = []
        for r in renames:
            kept = [not isinstance(r, AliasRetarget) and keeps.kept(e.path, snapshot.source(e.path).line(e.start))
                    for e in r.edits]
            held = r.held if isinstance(r, AliasRetarget) else []
            dropped.append([*held, *(e for e, k in zip(r.edits, kept, strict=True) if k)])
            r.edits = [e for e, k in zip(r.edits, kept, strict=True) if not k]
            r.blindspots = [b for b in r.blindspots if not keeps.kept(b.path, b.line)]
            r.leftovers = [f for f in r.leftovers if not keeps.kept(f.path, f.line, mark=False)]
        keeps.check()
        return dropped

    def merged(self, renames: list[Renaming], indexes: list[int]) -> list[TextEdit]:
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

    def check_names(self, renames: list[Renaming], resolved: list[_Resolved], dropped: list[list[TextEdit]]) -> None:
        """`NameConflict` when a rename changes what a name means or meets a member of its class's namespace: each
        `new_name` entry alone against the code before the map, in map order, then every entry together."""
        entries = [
            EntryEdits(index=res.entry.index, new_name=r.new, edits=r.edits, kept=kept,
                       target=res.target_name if res.entry.retarget is not None else None,
                       binds=r.imports if isinstance(r, AliasRetarget) else [])
            for r, res, kept in zip(renames, resolved, dropped, strict=True)
        ]
        members = [
            (entry, RenamedMember(entry=entry.index, new_name=r.new, site=site, cls=cls))
            for r, entry in zip(renames, entries, strict=True) if isinstance(r, SymbolRename) and r.new != r.old
            for site, cls in r.renamed_members()
        ]
        rels = [p.relative_to(self.root).as_posix() for p in language_files(self.root, "python")]
        folders = sorted({"", *(f.path for f in self.project.get_source_folders())})
        bindings = BindingCheck(rels, folders, self.session.snapshot.source)
        namespace = MemberCheck(Hierarchy(self.project, rels, self.session.snapshot.source), self.session.snapshot.text)
        passes = [[e] for e, res in zip(entries, resolved, strict=True) if res.entry.new_name is not None]
        for group in passes if passes == [entries] else [*passes, entries]:
            renamed = [m for e, m in members if any(e is g for g in group)]
            found = first_conflict(
                bindings.conflicts(group) + namespace.conflicts(renamed, {m.site for m in renamed}),
                self.session.snapshot.source,
            )
            if found is not None:
                raise found

    def refusal(self, renames: list[Renaming]) -> list[str]:
        """The lines refusing the map, or none when it may proceed."""
        refusals = _unique(f for r in renames if isinstance(r, AliasRetarget) for f in r.refusals)
        if refusals:
            return [f.text for f in refusals]
        blindspots = _unique(b for r in renames for b in r.blindspots)
        stand_ins = _unique(s for r in renames for s in r.stand_in_findings())
        blind = [] if self.options.allow_blindspots else blindspots
        if not blind and not stand_ins:
            return []
        attrs = ", .".join(dict.fromkeys(r.old for r in renames if r.blindspots))
        closing = [message("refactor.blindspots", count=len(blind), attr=attrs)] if blind else []
        return [*(f.text for f in blindspots), *(f.text for f in stand_ins), *closing]

    def findings(self, renames: list[Renaming]) -> list[Finding]:
        """The blind spots let through and the leftovers, each group sorted."""
        blindspots = _unique(b for r in renames for b in r.blindspots)
        unique = {(f.path, f.line, f.col, f.text): f for r in renames for f in r.leftovers}
        leftovers = [unique[k] for k in sorted(unique)]
        return [*blindspots, *leftovers]

    def check_conflicts(self, renames: list[Renaming]) -> None:
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


def source_bytes(project: Project) -> dict[str, bytes]:
    """Every file rope or la counts as Python source, its bytes read before rope computes a change set from them."""
    root = Path(project.address).resolve()
    rels = {path.relative_to(root).as_posix() for path in language_files(root, "python")}
    rels |= {f.path for f in project.get_python_files()}
    return {rel: (root / rel).read_bytes() for rel in sorted(rels)}


def change_set_writes(changes: ChangeSet, before: dict[str, bytes]) -> tuple[list[FileWrite], list[FileMove]]:
    """A rope change set as writes and moves, each write's old bytes as `before` holds them; `FileChanged` for a
    write `before` does not hold, as its bytes cannot be checked against what rope read."""
    writes: list[FileWrite] = []
    moves: list[FileMove] = []
    for change in changes.changes:
        if isinstance(change, ChangeContents):
            file: File = change.resource
            file.read()
            data = unicode_to_file_data(change.new_contents, newlines=file.newlines)
            old = before.get(file.path)
            if old is None:
                raise FileChanged(file.path)
            writes.append(FileWrite(rel=file.path, old=old, new=bytes(data)))
        elif isinstance(change, MoveResource):
            moves.append(FileMove(rel=change.resource.path, dest=change.new_resource.path))
    return writes, moves


def emit(project: Project, headers: list[str], changes: ChangeSet, apply_: bool, writes: list[FileWrite],
         moves: list[FileMove], *, moved_code: bool = False, edits: dict[str, list[Edit]] | None = None) -> None:
    """Print the headers and the changes sorted by path, the realigned baseline included, then write them with
    `--apply`; `BaselineFailed` when the checker fails."""
    aligned = align(Path(project.address), writes, moves, edits=edits, moved_code=moved_code)
    described = [(c.resource.path, c.get_description()) for c in changes.changes]
    if aligned is not None:
        for warning in aligned.warnings:
            print(warning, file=sys.stderr)
    if aligned is not None and aligned.write is not None:
        described.append((aligned.write.rel, aligned.description))
        writes = [*writes, aligned.write]
    ordered = sorted(described)
    if apply_:
        verify(Path(project.address).resolve(), writes)
    print("\n".join(headers) + "\n\n\n" + "".join(text + "\n" for _, text in ordered))
    touched = [path for path, _ in ordered]
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
        modules = [r for r in resolved if r.renamer is not None and r.renamer._is_renaming_a_module()]  # pyright: ignore[reportPrivateUsage]
        if modules:
            if len(resolved) > 1:
                raise RefactorError(message(_CANNOT_RENAME))
            return module_rename(modules[0])
        renames = engine.build(resolved)
        engine.compute(renames)
    except (RefactoringError, BadIdentifierError):
        raise RefactorError(message(_CANNOT_RENAME)) from None
    except LanguageServerError:
        raise RefactorError(message("refactor.pyright-failed")) from None
    except ConfigError as exc:
        raise RefactorError(str(exc)) from None
    except UnresolvedBase as base:
        root = engine.root
        path = (base.path.relative_to(root) if base.path.is_relative_to(root) else base.path).as_posix()
        raise RefactorError(message("refactor.unresolved-base", name=base.name, path=path, line=base.line)) from None
    keeps = Keeps(options.keep, engine.root)
    engine.retarget(renames, keeps)
    dropped = engine.keep(renames, keeps)
    engine.check_conflicts(renames)
    edits = engine.merged(renames, [r.entry.index for r in resolved])
    engine.check_names(renames, resolved, dropped)
    refusal = engine.refusal(renames)
    if refusal:
        raise Refused(refusal)
    if options.unsure:
        print(message("refactor.unsure-warning"))
    for finding in engine.findings(renames):
        print(finding.text, file=sys.stderr)
    changes, writes = engine.outputs(edits)
    by_file: dict[str, list[Edit]] = {}
    for e in edits:
        by_file.setdefault(e.path, []).append((e.start, e.end, len(e.new_text)))
    emit(project, [r.header() for r in renames], changes, apply_, writes, [], edits=by_file)
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
