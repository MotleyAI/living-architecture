"""`dr-refactor rename-map`: rename, retarget and module entries resolved against the code before the map, checked
before any reference search, computed on one snapshot and one occurrence index (one language server, started only
when needed), printed as one diff with every move and written all or nothing. `rename` and `retarget` are one-entry
maps."""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

from rope.base.change import ChangeContents, ChangeSet, MoveResource
from rope.base.fscommands import unicode_to_file_data
from rope.base.project import Project
from rope.base.resources import File

from living_architecture.config import ConfigError, find_repo_root, load_config, source_files
from living_architecture.contract import manifest, message
from living_architecture.lang import LanguageServerError
from living_architecture.refactor.baseline_align import (
    BaselineFailed,
    align,
    baseline_runs,
    config_error,
    probe,
)
from living_architecture.refactor.bindings import BindingCheck, EntryEdits, first_conflicts
from living_architecture.refactor.diff_render import edit_description, move_description
from living_architecture.refactor.entry_location import Entry, EntryLocator
from living_architecture.refactor.index_cache import IndexCache
from living_architecture.refactor.keyed import TypeFacts, UnresolvedBase
from living_architecture.refactor.literal_rename import LiteralRename, check_value, literal_member_at
from living_architecture.refactor.locators import RefactorError, cannot_rename, project_rel, resolve
from living_architecture.refactor.map_file import MapEntry, MapError, locator_text
from living_architecture.refactor.member_namespace import Hierarchy, MemberCheck, RenamedMember
from living_architecture.refactor.member_scan import probe_round
from living_architecture.refactor.module_rename import (
    ModuleRename,
    ModuleResult,
    final_paths,
    innermost_first,
    move_conflicts,
    valid_module_name,
)
from living_architecture.refactor.move_edits import NameConflict
from living_architecture.refactor.occurrence_index import (
    ClassFactSource,
    RunIndex,
    ServerSession,
    candidate_files,
)
from living_architecture.refactor.outcomes import Finding, covers
from living_architecture.refactor.position_map import Edit
from living_architecture.refactor.progress import (
    Progress,
    Refusal,
    Refused,
    checker_cause,
    entry_refusal,
    refusal,
    unique,
)
from living_architecture.refactor.python_project import Snapshot
from living_architecture.refactor.python_source import SourceFile, nfkc
from living_architecture.refactor.rename_union import (
    RenameOptions,
    RenameResult,
    Session,
    SymbolRename,
)
from living_architecture.refactor.retarget import (
    AliasRetarget,
    ImportNeed,
    Location,
    TargetHome,
    attribute_definition,
    definition,
    imported_module,
    module_name,
)
from living_architecture.refactor.retarget_imports import plan_imports
from living_architecture.refactor.rope_patches import walk_gap_line
from living_architecture.refactor.routing import language_files
from living_architecture.refactor.sites import Keeps, Site, keep_spells, resolve_keeps
from living_architecture.refactor.symbol_path import LocatorError, declaration_scope, locate
from living_architecture.refactor.text_edits import TextEdit, apply_edits, merge_edits
from living_architecture.refactor.timings import timed
from living_architecture.refactor.writer import FileChanged, FileMove, FileWrite, apply, verify

_WORD = re.compile(r"\w+")


Renaming = SymbolRename | LiteralRename | ModuleRename


def _live(r: Renaming) -> bool:
    """`r` changes a name: its new name is not its old one (as Python reads a module's)."""
    return r.new != r.old and not (isinstance(r, ModuleRename) and r.same)


def _symbol_groups(renames: dict[int, Renaming]) -> dict[str, list[int]]:
    """The indexes of the non-module renames by old name, in the order of their first entry."""
    groups: dict[str, list[int]] = {}
    for i, r in renames.items():
        if not isinstance(r, ModuleRename):
            groups.setdefault(r.old, []).append(i)
    return groups


class _Resolved:
    """An entry located: its file, what it names, its canonical symbol and its intent, and every map index merged
    into it."""

    def __init__(self, entry: MapEntry, rel: str, located: Entry | None, key: tuple[object, ...],
                 literal: ast.Constant | None = None, offset: int = 0) -> None:
        self.entry = entry
        self.indexes = [entry.index]
        self.shown = ""
        self.rel = rel
        self.located = located
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

    def old(self) -> str:
        if self.literal is not None:
            return str(self.literal.value)
        return self.located.name if self.located else ""

    def is_module(self) -> bool:
        return self.located is not None and self.located.kind == "module"


def _leaves(sibling: Entry, name: str, holder: _Resolved | None, resolved: list[_Resolved]) -> bool:
    """`sibling` stops being named `name`: the entry renaming it (`holder`) gives it another name; with no such entry,
    one sharing a site with it leaves it undecided."""
    if holder is None:
        return any(o.located is not None and set(o.located.sites) & set(sibling.sites) for o in resolved)
    return holder.entry.new_name is None or nfkc(holder.entry.new_name) != name


def _normalize(text: str) -> str:
    """The text as rope reads it."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _unique(findings: Iterable[Finding]) -> list[Finding]:
    """`findings` in path, line and column order, each once: entries sharing an old name scan its sites once."""
    return sorted({(f.path, f.line, f.col, f.text): f for f in findings}.values(), key=lambda f: (f.path, f.line, f.col))


def _import_of(source: SourceFile, alias: ast.AST) -> ast.ImportFrom | None:
    """The `from ... import` statement holding `alias`."""
    assert source.tree is not None
    return next((s for s in source.nodes if isinstance(s, ast.ImportFrom) and any(a is alias for a in s.names)), None)


def _texts(findings: Iterable[Finding]) -> list[Refusal]:
    return [refusal(f.text) for f in findings]


def _name_conflict(conflict: NameConflict) -> Refusal:
    return refusal(message("refactor.name-conflict", name=conflict.name, path=conflict.path, line=conflict.line))


def server_failed(exc: LanguageServerError) -> Refusal:
    return Refusal(lines=(message("refactor.pyright-failed"), *checker_cause(exc.kind, exc.error, exc.code, exc.stderr)))


def baseline_failed(exc: BaselineFailed) -> Refusal:
    return Refusal(lines=(message("refactor.baseline-failed", language="python"), *exc.cause))


def failure(exc: Exception, root: Path) -> Refusal | None:
    """The finding of an exception that refuses one entry, or None for any other."""
    if isinstance(exc, (LocatorError, MapError)):
        return refusal(str(exc), 2)
    if isinstance(exc, (RefactorError, ConfigError)):
        return refusal(str(exc))
    if isinstance(exc, UnresolvedBase):
        path = (exc.path.relative_to(root) if exc.path.is_relative_to(root) else exc.path).as_posix()
        return refusal(message("refactor.unresolved-base", name=exc.name, path=path, line=exc.line))
    return None


_ENTRY_ERRORS = (LocatorError, MapError, RefactorError, ConfigError, UnresolvedBase)


def undecodable(snapshot: Snapshot, rels: Iterable[str], olds: Iterable[str], keeps: Keeps) -> list[Finding]:
    """`refactor.undecodable` for each of `rels` that does not decode, per old name its bytes hold, unless kept."""
    out: list[Finding] = []
    for rel in sorted(rels):
        encoding = snapshot.undecodable(rel)
        if encoding is None or not any(old.encode() in snapshot.data(rel) for old in olds) or keeps.kept(rel, None):
            continue
        out += [Finding(path=rel, line=0, col=0, text=message("refactor.undecodable", path=rel, encoding=encoding, old=old))
                for old in sorted(set(olds)) if old.encode() in snapshot.data(rel)]
    return out


def walker_gaps(root: Path, text: Callable[[str], str], names: set[str], rels: list[str] | None = None) -> list[Refusal]:
    """A `refactor.rope-walk` finding for each Python source spelling one of `names` (of `rels`, when given) that
    rope's walker cannot cover, in path order."""
    out: list[Refusal] = []
    walked = rels if rels is not None else [p.relative_to(root).as_posix() for p in language_files(root, "python")]
    for rel in sorted(walked):
        try:
            source = _normalize(text(rel))
        except (OSError, UnicodeDecodeError, LookupError):
            continue
        if not any(name in source for name in names):
            continue
        try:
            line = walk_gap_line(source)
        except (SyntaxError, ValueError):
            continue
        if line is not None:
            out.append(refusal(message("refactor.rope-walk", path=rel, line=line)))
    return out


def baseline_probe(project: Path, source: Path) -> list[Refusal]:
    """The config's error, else the configured checker run once on `source` when the baseline phase will run; its
    failure."""
    error = config_error(project)
    if error is not None:
        return [refusal(error, 2)]
    if not baseline_runs(project):
        return []
    try:
        with timed("baseline"):
            probe(project, source)
    except BaselineFailed as exc:
        return [baseline_failed(exc)]
    return []


def site_checks(sites: list[tuple[str, str]], root: Path) -> tuple[list[Refusal], set[tuple[str, str]]]:
    """`refactor.site-missing` for each (option, raw) site naming nothing; the missing ones."""
    out: list[Refusal] = []
    missing: set[tuple[str, str]] = set()
    for option, raw in sites:
        if Site.parse(raw, root).missing(root):
            out.append(refusal(message("refactor.site-missing", option=option, site=raw), 2))
            missing.add((option, raw))
    return out, missing


def editable_files(root: Path, docs: bool) -> dict[str, bool]:
    """The files a rename can edit: each Python source (True), and with `docs` each prose file (False)."""
    out = {path.relative_to(root).as_posix(): True for path in language_files(root, "python")}
    if docs:
        extensions = tuple(manifest()["dr-refactor"]["prose_extensions"])
        for rel in sorted(source_files(root, [])):
            if rel.endswith(extensions):
                out.setdefault(rel, False)
    return out


def keep_checks(keeps: list[str], root: Path, editable: dict[str, bool], text: Callable[[str], str], names: set[str],
                moved: list[str], skipped: set[tuple[str, str]], *, docs: bool) -> list[Refusal]:
    """`refactor.keep-unmatched` for each line keep on a line spelling none of `names` (in a comment only with `docs`)
    and in no moved file."""
    out: list[Refusal] = []
    for raw in keeps:
        site = Site.parse(raw, root)
        if ("--keep", raw) in skipped or site.line is None:
            continue
        if not keep_spells(site, editable, text, names, moved, docs=docs):
            out.append(refusal(message("refactor.keep-unmatched", site=raw), 2))
    return out


def _spelled(entry: MapEntry) -> str | None:
    """The name an entry's locator spells: the last word of its symbol path."""
    words = _WORD.findall(entry.locator.symbol or "")
    return words[-1] if words else None


LeftoverKey = tuple[str, int, int, str]


class Leftovers:
    """The run's leftover findings, each `(path, line, col, text)` held once with every `end` seen for it."""

    def __init__(self) -> None:
        self._found: dict[LeftoverKey, tuple[Finding, set[int | None]]] = {}

    def add(self, finding: Finding) -> None:
        key = (finding.path, finding.line, finding.col, finding.text)
        if key in self._found:
            self._found[key][1].add(finding.end)
        else:
            self._found[key] = (finding, {finding.end})

    def uncovered(self, edits: dict[str, list[TextEdit]]) -> dict[LeftoverKey, Finding]:
        """Each finding one of whose spans no edit of `edits` (by path) covers."""
        return {key: f for key, (f, ends) in self._found.items()
                if any(not any(covers(f.path, f.col, end, e) for e in edits.get(f.path, ())) for end in ends)}


class RenameMap:
    """The entries of a map computed as one refactor."""

    def __init__(self, root: Path, entries: list[MapEntry], options: RenameOptions, map_shown: str,
                 progress: Progress) -> None:
        self.stub: str | None = None
        self.entries = entries
        self.options = options
        self.map_shown = map_shown
        self.progress = progress
        self.session = Session(root)
        self.root = self.session.root
        self.server = ServerSession(self.root, self.session.read)
        self._index: RunIndex | None = RunIndex(self.root, self.session.load, self.server, IndexCache(self.root))
        self._locator: EntryLocator | None = EntryLocator(self.root, self._definitions, self.session.snapshot,
                                                          self.session.layout)
        self.class_facts: ClassFactSource | None = None
        self.leftovers = Leftovers()
        self._results: dict[int, RenameResult] = {}
        self._needs: dict[int, list[ImportNeed]] = {}
        self.stopped = False
        # The refusals a `[rules]` line printed, and the renames whose group printed its line.
        self.printed: list[Refusal] = []
        self.lined: set[int] = set()
        self.by_index: dict[int, _Resolved] = {}

    def _refuse(self, entry: MapEntry | _Resolved, found: Refusal) -> Refusal:
        """`found` as the refusal of `entry`, with every map index merged into it."""
        if isinstance(entry, _Resolved):
            return entry_refusal(entry.indexes, entry.shown, found)
        return entry_refusal([entry.index], locator_text(self.root, entry), found)

    def _failure(self, entry: MapEntry | _Resolved, exc: Exception) -> list[Refusal]:
        found = failure(exc, self.root)
        return [self._refuse(entry, found)] if found is not None else []

    @property
    def index(self) -> RunIndex:
        assert self._index is not None
        return self._index

    @property
    def locator(self) -> EntryLocator:
        assert self._locator is not None
        return self._locator

    # ---- resolve

    def _locate(self, entry: MapEntry) -> tuple[str, int]:
        rel = project_rel(self.root, entry.path)
        if entry.module:
            return rel, 0
        offset, _ = resolve(entry.locator, self.session.snapshot.source(rel), entry.file)
        return rel, offset

    def _definitions(self, rel: str, offset: int) -> list[tuple[Path, int]]:
        """The run's language server's `definition` at `offset` of `rel`, opened as the snapshot holds it."""
        server = self.server.get()
        server.open(self.root / rel, self.session.snapshot.text(rel))
        return [(s.path, s.start) for s in server.definition(self.root / rel, offset)]

    def _literal(self, entry: MapEntry, rel: str, offset: int) -> _Resolved | None:
        """The entry as a `Literal` member rename, when its locator names a string of a `Literal[...]`."""
        source = self.session.snapshot.source(rel)
        node = literal_member_at(source, offset)
        if node is None:
            return None
        if entry.new_name is None:
            raise cannot_rename()
        check_value(entry.new_name)
        return _Resolved(entry, rel, None, ("literal", rel, source.span(node)[0]), literal=node)

    def _resolve(self, entry: MapEntry) -> _Resolved:
        """`entry` located; `refactor.cannot-rename` for a module rename whose new name cannot name a module."""
        located = self._locate(entry)
        if entry.module:
            found = self.locator.file_module(located[0])
            resolved = _Resolved(entry, located[0], found, found.key)
        else:
            literal = self._literal(entry, *located)
            if literal is not None:
                return literal
            found = self.locator.at(*located)
            resolved = _Resolved(entry, located[0], found, found.key, offset=located[1])
        if resolved.is_module() and entry.new_name is not None and not valid_module_name(entry.new_name):
            raise cannot_rename()
        if entry.retarget is not None:
            self._resolve_target(resolved)
        return resolved

    def _resolve_target(self, resolved: _Resolved) -> None:
        """The target beside the alias: declared or imported in the alias's class or module, or the name a re-export
        declaring the alias imports; LocatorError otherwise."""
        entry, rel, found = resolved.entry, resolved.rel, resolved.located
        assert found is not None
        source = self.session.snapshot.source(rel)
        alias = entry.locator.symbol or found.name
        refused = LocatorError(message("refactor.retarget-scope", target=entry.retarget, alias=alias))
        old = found.name
        alias_line = source.line(resolved.offset)
        alias_scope = declaration_scope(source, old, alias_line)
        if alias_scope is not None and isinstance(alias_scope[1], ast.alias):
            self._reexport_target(resolved, source, alias_scope, alias_line, refused)
            return
        try:
            located = locate(source, str(entry.retarget), entry.file)
        except LocatorError:
            raise refused from None
        word = _WORD.match(source.text, located.offset)
        def_rel, def_line = definition(found) or (None, None)
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
        try:
            target = self.locator.at(rel, located.offset, follow=True)
        except RefactorError:
            raise refused from None
        resolved.target_key = target.key
        if not isinstance(alias_scope[0], ast.Module):
            return
        home = definition(target)
        if imported:
            self._imported_home(resolved, source, target_scope[1], home, refused)
        else:
            resolved.home = TargetHome(module=module_name(self.session, rel), exported=resolved.target_name,
                                       local=resolved.target_name, definition=home)

    def _imported_home(self, resolved: _Resolved, source: SourceFile, node: ast.AST, found: Location | None,
                       refused: LocatorError) -> None:
        """The home of a target the alias's module imports by `node`; the target keyed by its home's declaration."""
        stmt = _import_of(source, node)
        if stmt is None or not isinstance(node, ast.alias):
            raise refused
        if resolved.target_key is not None and resolved.target_key[0] == "name":
            resolved.target_key = (*resolved.target_key[:3], node.name)
        resolved.home = TargetHome(module=imported_module(self.session, resolved.rel, stmt), exported=node.name,
                                   local=resolved.target_name, definition=found)

    def _reexport_target(self, resolved: _Resolved, source: SourceFile, alias_scope: tuple[ast.AST, ast.AST], line: int,
                         refused: LocatorError) -> None:
        """The alias declared by `from M import T as ALIAS` at module level: TARGET is `T` from `M`."""
        node = alias_scope[1]
        stmt = _import_of(source, node)
        assert isinstance(node, ast.alias)
        if stmt is None or not isinstance(alias_scope[0], ast.Module) or node.name != resolved.entry.retarget:
            raise refused
        module = imported_module(self.session, resolved.rel, stmt)
        found = attribute_definition(self.locator, module, node.name)
        resolved.target_name = node.name
        resolved.line = line
        span = source.name_span(node)
        if span is None:
            raise refused
        resolved.own = (resolved.rel, span[0])
        resolved.target_key = ("name", found[0], found[1], node.name) if found is not None else ("site", resolved.rel, line, node.name)
        resolved.home = TargetHome(module=module, exported=node.name, local=node.name, definition=found)

    def resolve(self) -> tuple[list[_Resolved], list[Refusal], bool]:
        """Every entry located, searching no reference: the resolved entries (duplicates merged), each failure in
        entry order, and whether every entry that failed spells a name."""
        out: list[_Resolved] = []
        failures: list[Refusal] = []
        spelled = True
        for entry in self.entries:
            try:
                resolved = self._resolve(entry)
            except _ENTRY_ERRORS as exc:
                failures += self._failure(entry, exc)
                spelled = spelled and _spelled(entry) is not None
                continue
            resolved.shown = locator_text(self.root, entry)
            first = next((r for r in out if r.key == resolved.key), None)
            if first is None:
                out.append(resolved)
            elif first.intent() != resolved.intent():
                failures.append(refusal(message("refactor.map-duplicate", map=self.map_shown, first=first.entry.index,
                                                second=entry.index), 2))
            else:
                first.indexes.append(entry.index)
        return out, failures, spelled

    # ---- checks

    def names(self, resolved: list[_Resolved]) -> set[str]:
        """Every resolved entry's old name, every retarget's target name, and the names failed entries spell."""
        names = {r.old() for r in resolved} | {r.target_name for r in resolved if r.target_name}
        resolved_indexes = {i for r in resolved for i in r.indexes}
        names |= {n for e in self.entries if e.index not in resolved_indexes and (n := _spelled(e)) is not None}
        return {n for n in names if n}

    def _moved(self, resolved: list[_Resolved]) -> list[str]:
        """The file or package a module rename moves."""
        return [r.located.module for r in resolved if r.located is not None and r.located.module is not None]

    def checks(self, resolved: list[_Resolved], spelled: bool) -> list[Refusal]:
        """Every check that needs no reference: sites, keeps and the checkers."""
        options = self.options
        sites = [("--with", raw) for raw in options.with_sites]
        sites += [("--without", raw) for raw in options.without_sites]
        sites += [("--keep", raw) for raw in options.keep]
        found, missing = site_checks(sites, self.root)
        if resolved and all(r.is_module() for r in resolved):
            found += [refusal(message("refactor.not-stand-in", site=raw), 2)
                      for option, raw in sites if option != "--keep" and (option, raw) not in missing]
        found += self._stub_checks(resolved)
        names = self.names(resolved)
        text = self.session.snapshot.text
        if spelled and options.keep and not any(r.literal is not None for r in resolved):
            editable = editable_files(self.root, options.docs)
            found += keep_checks(list(options.keep), self.root, editable, text, names, self._moved(resolved), missing,
                                 docs=options.docs)
        taken = {n: t for n, r in enumerate(resolved) if r.is_module() and (t := self._module(r).taken()) is not None}
        taken |= self.own_scope_conflicts(resolved)
        found += [self._refuse(resolved[n], _name_conflict(taken[n])) for n in sorted(taken)]
        if not resolved or not self._cached(resolved):
            try:
                self.server.get()
            except LanguageServerError as exc:
                found.append(server_failed(exc))
        source = self.root / resolved[0].rel if resolved else Path(self.entries[0].path)
        return found + [r for r in baseline_probe(self.root, source) if r not in found]

    def own_scope_conflicts(self, resolved: list[_Resolved]) -> dict[int, NameConflict]:
        """Each `new_name` entry of a symbol (by its place in `resolved`) whose declaring scope holds its new name: a
        declaration no entry renames away, else an earlier entry's renamed onto it (the latest entry's finding). A
        pair with a kept line, or one the entries do not decide, is left to the conflicts phase."""
        source = self.session.snapshot.source
        keeps = [Site.parse(raw, self.root) for raw in self.options.keep]

        def kept(entry: Entry) -> bool:
            return any(k.covers(rel, source(rel).line(start)) for rel, start in entry.sites for k in keeps)

        def conflict(r: _Resolved, site: tuple[str, int]) -> NameConflict:
            return NameConflict(str(r.entry.new_name), site[0], source(site[0]).line(site[1]))

        renames = [(n, r, r.located, nfkc(r.entry.new_name)) for n, r in enumerate(resolved)
                   if r.located is not None and r.entry.new_name is not None and not r.is_module()
                   and nfkc(r.entry.new_name) != r.located.name]
        by_key = {r.key: r for r in resolved}
        out: dict[int, NameConflict] = {}
        scopes: dict[tuple[tuple[str, int], str], list[tuple[int, _Resolved, Entry]]] = {}
        for n, r, located, new in renames:
            scope = self.locator.scope_id(located)
            if scope is not None:
                scopes.setdefault((scope, new), []).append((n, r, located))
            sibling = self.locator.sibling(located, new)
            if sibling is None or kept(located) or kept(sibling):
                continue
            if not _leaves(sibling, new, by_key.get(sibling.key), resolved):
                out[n] = conflict(r, sibling.sites[0])
        for meeting in scopes.values():
            if len(meeting) < 2 or any(kept(located) for _, _, located in meeting):
                continue
            ordered = sorted(meeting, key=lambda m: m[1].entry.index)
            out.setdefault(ordered[-1][0], conflict(ordered[-1][1], ordered[0][2].sites[0]))
        return out

    def _module(self, r: _Resolved) -> ModuleRename:
        assert r.located is not None
        return ModuleRename(self.session, self.locator, r.located, str(r.entry.new_name), self.options)

    def _stub_checks(self, resolved: list[_Resolved]) -> list[Refusal]:
        """`--stub` needs a module rename, each of a Python module file, and a configured stub; the stub's text."""
        if self.options.stub is None:
            return []
        modules = [self._module(r) for r in resolved if r.is_module()]
        if not modules or not all(m.stubbable() for m in modules):
            return [refusal(message("refactor.stub-not-module"), 2)]
        try:
            self.stub = load_config(find_repo_root(self.root)).refactor.python.moved_module_stub
        except ConfigError as exc:
            return [refusal(str(exc), 2)]
        return [] if self.stub is not None else [refusal(message("refactor.stub-unconfigured"), 2)]

    def _cached(self, resolved: list[_Resolved]) -> bool:
        """Fix the run's export request; whether the run can do without a language server: only module renames, or
        symbol renames whose export is cached, with no `Literal` member."""
        symbols = [r for r in resolved if not r.is_module()]
        if not symbols:
            return True
        names = {r.old() for r in symbols if r.literal is None}
        news = {str(r.entry.new_name) for r in symbols if r.literal is None and r.entry.new_name is not None}
        rels = self.session.python_files()
        candidates = candidate_files(rels, self.session.snapshot.text, self.session.snapshot.source, names)
        spelling = candidate_files(rels, self.session.snapshot.text, self.session.snapshot.source, news) if news else []
        cached = not names or self.index.prepare(names, [self.root / rel for rel in candidates], news,
                                                 [self.root / rel for rel in spelling])
        return cached and all(r.literal is None for r in resolved)

    # ---- references

    def build(self, resolved: list[_Resolved]) -> list[Renaming]:
        finals = {r.key: r.entry.new_name for r in resolved if r.entry.new_name is not None}
        renames: list[Renaming] = []
        for r in resolved:
            if r.is_module():
                renames.append(self._module(r))
            elif r.literal is not None:
                renames.append(LiteralRename(self.session, r.rel, r.literal, str(r.entry.new_name), self.options))
            elif r.entry.retarget is not None:
                renames.append(self._retarget(r, finals.get(r.target_key)))  # pyright: ignore[reportArgumentType]
            else:
                assert r.located is not None
                renames.append(SymbolRename(self.session, r.located, str(r.entry.new_name), self.options, site=self._site(r),
                                            locator=self.locator))
        return renames

    def _site(self, r: _Resolved) -> tuple[str, int]:
        return r.rel, r.offset

    def _retarget(self, r: _Resolved, final: str | None) -> AliasRetarget:
        """`r`'s retarget, `final` the new name of its target where another entry renames it: under an import `as`
        another name only the home's export is renamed, the local name stays."""
        assert r.located is not None
        home, target = r.home, r.target_name
        if final is not None and (home is None or home.exported == home.local):
            target = final
            home = home.model_copy(update={"exported": final, "local": final}) if home is not None else None
        elif final is not None and home is not None:
            home = home.model_copy(update={"exported": final})
        return AliasRetarget(self.session, r.located, target, self.options, site=self._site(r), locator=self.locator,
                             line=r.line, home=home, own=r.own, original=r.target_name, index=r.entry.index)

    def references(self, renames: list[Renaming], resolved: list[_Resolved]) -> dict[int, list[Refusal]]:
        """Each entry's renamed declarations, read from the run's occurrence index (exported first), announced as each
        entry starts; the entries that failed."""
        if any(isinstance(r, SymbolRename) for r in renames):
            self.index.build()
        failed: dict[int, list[Refusal]] = {}
        for n, (r, res) in enumerate(zip(renames, resolved, strict=True), 1):
            if self.stopped:
                break
            self.progress.item(n, len(renames), res.indexes, r.old, r.new)
            if not _live(r):
                continue
            try:
                r.prepare(self.index)
            except _ENTRY_ERRORS as exc:
                failed[n - 1] = self._failure(res, exc)
                self.stopped = self.options.fail_fast
        return failed

    def seed(self, renames: dict[int, Renaming], resolved: list[_Resolved], active: list[int],
             failed: dict[int, list[Refusal]]) -> TypeFacts:
        facts = TypeFacts(self.index, self.session.load)
        for i in active:
            try:
                renames[i].seed(facts)
            except UnresolvedBase as exc:
                failed[i] = self._failure(resolved[i], exc)
        live = [i for i in active if i not in failed]
        renamed = {site for i in live for site in renames[i].seeds}
        for i in live:
            renames[i].is_renamed = renamed.__contains__
        symbol_renames = [r for i in live if isinstance(r := renames[i], SymbolRename)]
        symbols = sorted({r.old for r in symbol_renames})
        if symbols:
            files = [(self.root / rel, self.session.snapshot.source(rel))
                     for rel in sorted({rel for r in symbol_renames for rel in r.candidates})]
            with timed("rules"):
                probe_round(self.index, files, symbols, self.session.load)
        return facts

    # ---- rules

    def _group_refusals(self, group: list[int], failed: dict[int, list[Refusal]]) -> list[Refusal]:
        own = [f for i in group for f in failed.get(i, [])]
        live = [self._results[i] for i in group if i not in failed]
        retargets = [f for r in live for f in r.refusals]
        blind = [] if self.options.allow_blindspots else [b for r in live for b in r.blindspots]
        stand_ins = [s for r in live for s in r.stand_ins]
        return unique([*own, *_texts(_unique([*retargets, *blind, *stand_ins]))])

    def rules(self, renames: dict[int, Renaming], resolved: list[_Resolved], failed: dict[int, list[Refusal]],
              facts: TypeFacts, keeps: Keeps) -> None:
        """Each module rename's keeps, then each old-name group's rules (module renames join none), in the order of its
        first entry, its line printed as it is done; each rename leaves `renames` as a result once done."""
        groups = _symbol_groups(renames)
        olds = {r.old for r in renames.values() if r.new != r.old and not isinstance(r, ModuleRename)}
        for i in [i for i, r in renames.items() if isinstance(r, ModuleRename)]:
            module = renames.pop(i)
            self._result(i, module, resolved[i], self._keep(module, keeps) if i not in failed else [])
        if groups:
            self.progress.phase("rules")
        for n, (old, group) in enumerate(groups.items(), 1):
            live = [i for i in group if renames[i].new != old]
            self._group_rules(live, renames, resolved, failed, facts)
            dropped = {i: self._finish(renames[i], olds, keeps) for i in live if i not in failed}
            for i in group:
                self._result(i, renames.pop(i), resolved[i], dropped.get(i, []))
            refused = self._group_refusals(group, failed)
            indexes = sorted(index for i in group for index in resolved[i].indexes)
            news = ", ".join(dict.fromkeys(self._results[i].new for i in group))
            self.progress.result(n, len(groups), indexes, old, news, [line for f in refused for line in f.lines])
            self.printed += refused
            self.lined |= set(group)
            if refused and self.options.fail_fast:
                self.stopped = True
                break

    def _result(self, i: int, r: Renaming, res: _Resolved, kept: list[TextEdit]) -> None:
        """`r` as the result of rename `i`; a retarget's import needs set aside for the import plan."""
        if isinstance(r, AliasRetarget):
            self._needs[i] = r.needs
        target = res.target_name if res.entry.retarget is not None else None
        self._results[i] = r.result(res.entry.index, target, kept)

    def _group_rules(self, group: list[int], renames: dict[int, Renaming], resolved: list[_Resolved],
                     failed: dict[int, list[Refusal]], facts: TypeFacts) -> None:
        for i in group:
            if i in failed:
                continue
            try:
                renames[i].rules(self.index, facts)
            except _ENTRY_ERRORS as exc:
                failed[i] = self._failure(resolved[i], exc)
                renames[i].edits = []

    def _finish(self, r: Renaming, olds: set[str], keeps: Keeps) -> list[TextEdit]:
        """`r`'s edits finished, merged, retargeted and filtered by the keeps; the edits the keeps dropped."""
        r.renamed_names = olds
        r.finish()
        r.edits = merge_edits(r.edits)
        if isinstance(r, AliasRetarget):
            with timed("rules"):
                r.retarget(keeps.kept)
        return self._keep(r, keeps)

    def end_rules(self, renames: dict[int, Renaming], resolved: list[_Resolved]) -> list[RenameResult]:
        """The end of `rules` on every path: each rename not yet a result made one as it stands, the retargets'
        imports planned once (unless stopped), then the phase's working state released; every result, in map
        order."""
        while renames:
            i, r = renames.popitem()
            self._result(i, r, resolved[i], [])
        results = [self._results[i] for i in sorted(self._results)]
        self._results = {}
        if not self.stopped:
            self._imports(results)
        self._needs = {}
        self.release()
        return results

    def _imports(self, results: list[RenameResult]) -> None:
        """The imports every retarget's sites need, planned once."""
        needs = [n for i in sorted(self._needs) for n in self._needs[i]]
        if not needs:
            return
        with timed("rules"):
            planned = plan_imports(self.session, needs)
        by_entry = {r.entry: r for r in results}
        for entry, edit in planned:
            by_entry[entry].imports.append(edit)
        for r in results:
            r.edits += r.imports

    def release(self) -> None:
        """Close the index (saving its cache), keeping only its class facts, and the server; drop the locator and the
        parsed files."""
        self.class_facts = self.index.class_fact_source()
        self.index.close()
        self._index = None
        self.server.close()
        self._locator = None
        self.session.drop_parsed()

    def _keep(self, r: Renaming, keeps: Keeps) -> list[TextEdit]:
        """Drop every edit, blind spot and leftover of `r` at a kept site (a retarget's are dropped already), and a
        module's move under a whole-path keep, the rest of its leftovers moved to the run's; the dropped edits."""
        snapshot = self.session.snapshot
        if isinstance(r, ModuleRename) and r.move is not None and keeps.kept(r.move.rel, None):
            r.move = None
        kept = [not isinstance(r, AliasRetarget) and keeps.kept(e.path, snapshot.source(e.path).line(e.start))
                for e in r.edits]
        held = r.held if isinstance(r, AliasRetarget) else []
        dropped = [*held, *(e for e, k in zip(r.edits, kept, strict=True) if k)]
        r.edits = [e for e, k in zip(r.edits, kept, strict=True) if not k]
        r.blindspots = [b for b in r.blindspots if not keeps.kept(b.path, b.line)]
        for f in r.leftovers:
            if not keeps.kept(f.path, f.line, mark=False):
                self.leftovers.add(f)
        r.leftovers = []
        if isinstance(r, SymbolRename):
            r.unresolved = [f for f in r.unresolved if not keeps.kept(f.path, f.line)]
        return dropped

    # ---- the final report

    def merged(self, results: list[RenameResult]) -> tuple[list[TextEdit], list[Refusal]]:
        """Every entry's edits, identical ones merged; a `refactor.map-conflict` for each site two entries rewrite
        differently."""
        tagged = sorted(
            {(e, r.entry) for r in results for e in r.edits},
            key=lambda t: (t[0].path, t[0].start, t[0].end, t[1]),
        )
        out: list[TextEdit] = []
        owner: list[int] = []
        conflicts: list[Refusal] = []
        for edit, index in tagged:
            if out and out[-1] == edit:
                continue
            if out and out[-1].path == edit.path and edit.start < out[-1].end:
                line = self.session.snapshot.source(edit.path).line(edit.start)
                first, second = sorted((owner[-1], index))
                conflicts.append(refusal(message("refactor.map-conflict", path=edit.path, line=line, first=first,
                                                 second=second)))
                continue
            out.append(edit)
            owner.append(index)
        return out, unique(conflicts)

    def _final_paths(self, results: list[RenameResult]) -> dict[str, str]:
        """Each project file the module renames among `results` move, to its path once every move is made."""
        moves = [r.move for r in results if isinstance(r, ModuleResult) and r.move is not None]
        return final_paths(self.session.all_python_files(), moves) if moves else {}

    def check_names(self, results: list[RenameResult], edits: list[TextEdit]) -> dict[int, NameConflict]:
        """Each entry's first name conflict, by map index, on the code after every entry's edits (`edits` merged) and
        every move: the moves that meet, else the names and the members."""
        snapshot = self.session.snapshot
        entries = [EntryEdits(index=r.entry, new_name=r.new, edits=r.edits, kept=r.kept, target=r.target, binds=r.imports)
                   for r in results]
        members = [RenamedMember(entry=r.entry, new_name=r.new, site=site, cls=cls)
                   for r in results if r.new != r.old for site, cls in r.renamed_members(snapshot)]
        assert self.class_facts is not None
        rels = self.session.python_files()
        moved = move_conflicts([r for r in results if isinstance(r, ModuleResult)], edits, snapshot.source, rels)
        if moved:
            return first_conflicts(moved, snapshot.source)
        bindings = BindingCheck(rels, self.session.source_folders(), snapshot.source)
        namespace = MemberCheck(Hierarchy(self.root, rels, snapshot.source, self.class_facts), snapshot.text)
        [bound] = bindings.conflicts([entries], self._final_paths(results))
        return first_conflicts(bound + namespace.conflicts(members, {m.site for m in members}), snapshot.source)

    def keyed_conflicts(self, results: list[RenameResult], edits: list[TextEdit]) -> dict[int, NameConflict]:
        """Each rename's first renamed keyword or key meeting its new name after `edits`, by map index."""
        out: dict[int, NameConflict] = {}
        for r in results:
            try:
                r.check_conflicts(self.session.snapshot, r.edits, edits)
            except NameConflict as conflict:
                out[r.entry] = conflict
        return out

    def resolve_sites(self, results: list[RenameResult], keeps: Keeps) -> list[Refusal]:
        """Site resolution over the final edits: each unneeded whole-path keep's warning printed; each `--with` or
        `--without` site no member entry's stand-ins hold, then each line keep that matched nothing."""
        matched = {raw for r in results if r.member for raw in r.matched_sites}
        out = [refusal(message("refactor.not-stand-in", site=raw), 2)
               for raw in (*self.options.with_sites, *self.options.without_sites) if raw not in matched]
        source = self.session.snapshot.source
        warnings, unmatched = resolve_keeps(keeps, ((e.path, source(e.path).line(e.start)) for r in results for e in r.edits))
        for warning in warnings:
            print(warning, file=sys.stderr)
        return out + unmatched

    def report(self, results: list[RenameResult], failed: dict[int, list[Refusal]],
               sites: list[Refusal]) -> tuple[list[TextEdit], list[Refusal]]:
        """The merged edits and the final report, holding what no `[rules]` line printed: the failures of entries
        whose group printed none, each entry's first name conflict or the map conflicts (not after a stop or a
        refusing site finding), then the site findings, then the blind-spot count."""
        live = [r for i, r in enumerate(results) if i not in failed]
        own = [f for i in sorted(failed) if i not in self.lined for f in failed[i]]
        blind = [] if self.options.allow_blindspots else _unique(b for r in live for b in r.blindspots)
        edits: list[TextEdit] = []
        conflicts: list[Refusal] = []
        if not self.stopped and not sites:
            self.progress.phase("conflicts")
            with timed("conflicts"):
                edits, conflicts = self.merged(results)
                if not conflicts:
                    conflicts = self._name_conflicts(results, live, edits)
        attrs = ", .".join(dict.fromkeys(r.old for r in live if r.blindspots))
        closing = [refusal(message("refactor.blindspots", count=len(blind), attr=attrs))] if blind else []
        return edits, unique([*own, *conflicts, *sites, *closing])

    def _name_conflicts(self, results: list[RenameResult], live: list[RenameResult], edits: list[TextEdit]) -> list[Refusal]:
        """Each entry's first name conflict, by map index: a renamed keyword or key meeting its new name, a binding."""
        found: dict[int, list[NameConflict]] = {}
        for by_entry in (self.keyed_conflicts(live, edits), self.check_names(results, edits)):
            for index, conflict in by_entry.items():
                found.setdefault(index, []).append(conflict)
        return [self._refuse(self.by_index[index], _name_conflict(min(found[index], key=lambda c: (c.path, c.line))))
                for index in sorted(found)]

    def findings(self, results: list[RenameResult], edits: list[TextEdit], listed: list[Finding]) -> list[Finding]:
        """The blind spots let through, then the leftovers no entry's `edits` rewrite with the `listed` files, sorted."""
        blindspots = _unique(b for r in results for b in r.blindspots)
        by_path: dict[str, list[TextEdit]] = {}
        for e in edits:
            by_path.setdefault(e.path, []).append(e)
        unique_ = self.leftovers.uncovered(by_path)
        unique_ |= {(f.path, f.line, f.col, f.text): f for f in listed}
        unique_ |= {(f.path, f.line, f.col, f.text): f for r in results for f in r.unresolved}
        leftovers = [unique_[k] for k in sorted(unique_)]
        return [*blindspots, *leftovers]

    def outputs(self, edits: list[TextEdit]) -> tuple[list[tuple[str, str]], list[FileWrite]]:
        """Each changed file's printed diff, and the writes."""
        return changes_of(self.session.snapshot, edits)

    # ---- the run

    def moves(self, results: list[RenameResult]) -> tuple[list[tuple[str, str]], list[FileMove], list[FileWrite]]:
        """Each module rename's move pair as printed, the moves innermost first, and with `--stub` each moved module
        file's stub."""
        modules = [r for r in results if isinstance(r, ModuleResult)]
        moves = [r.move for r in modules if r.move is not None]
        removal = self.options.stub
        stubs = [] if self.stub is None or removal is None else [
            s for r in modules if (s := r.stub(self.session, self.stub, removal))]
        described = [(m.rel, move_description(m.rel, m.dest)) for m in moves]
        described += [(s.rel, edit_description(s.rel, "", s.new.decode())) for s in stubs]
        return described, innermost_first(moves), stubs

    def run(self, apply_: bool) -> int:
        try:
            self.progress.phase("resolve")
            with timed("resolve"):
                resolved, failures, spelled = self.resolve()
                self.by_index = {r.entry.index: r for r in resolved}
            self.progress.phase("checks")
            failures += self.checks(resolved, spelled)
            if failures:
                raise Refused(failures)
            self.progress.phase("references")
            keeps = Keeps(self.options.keep, self.root)
            results, failed = self.rename(resolved, keeps)
        finally:
            self.server.close()
            if self._index is not None:
                self._index.close()
        olds = [r.old for r in results if r.live()]
        listed = undecodable(self.session.snapshot, self.session.all_python_files(), olds, keeps)
        sites = [] if self.stopped or failed else self.resolve_sites(results, keeps)
        edits, refusals = self.report(results, failed, sites)
        if refusals or self.printed:
            raise Refused(refusals, self.printed)
        if self.options.unsure:
            print(message("refactor.unsure-warning"))
        for finding in self.findings(results, edits, listed):
            print(finding.text, file=sys.stderr)
        described, writes = self.outputs(edits)
        moved, moves, stubs = self.moves(results)
        by_file: dict[str, list[Edit]] = {}
        for e in edits:
            by_file.setdefault(e.path, []).append((e.start, e.end, len(e.new_text)))
        emit(self.root, [r.header for r in results], [*described, *moved], apply_, writes, moves, self.progress,
             edits=by_file, creates=stubs)
        return 0

    def rename(self, resolved: list[_Resolved], keeps: Keeps) -> tuple[list[RenameResult], dict[int, list[Refusal]]]:
        """Every entry's references and rules, ending `rules` on every path: each entry's result, and the entries
        that failed."""
        renames = dict(enumerate(self.build(resolved)))
        failed = self.references(list(renames.values()), resolved)
        if not self.stopped:
            self._rules(renames, resolved, failed, keeps)
        return self.end_rules(renames, resolved), failed

    def _rules(self, renames: dict[int, Renaming], resolved: list[_Resolved], failed: dict[int, list[Refusal]],
               keeps: Keeps) -> None:
        active = [i for i, r in renames.items() if _live(r) and i not in failed]
        facts = self.seed(renames, resolved, active, failed)
        self.rules(renames, resolved, failed, facts, keeps)


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


def changes_of(snapshot: Snapshot, edits: list[TextEdit]) -> tuple[list[tuple[str, str]], list[FileWrite]]:
    """Each file `edits` change, by path: its printed diff, and its write."""
    described: list[tuple[str, str]] = []
    writes: list[FileWrite] = []
    for rel in sorted({e.path for e in edits}):
        raw = snapshot.text(rel)
        text = apply_edits(raw, [e for e in edits if e.path == rel])
        if text == raw:
            continue
        described.append((rel, edit_description(rel, raw, text)))
        writes.append(FileWrite(rel=rel, old=snapshot.data(rel), new=snapshot.encode(rel, text)))
    return described, writes


def emit(root: Path, headers: list[str], described: list[tuple[str, str]], apply_: bool, writes: list[FileWrite],
         moves: list[FileMove], progress: Progress, *, moved_code: bool = False,
         edits: dict[str, list[Edit]] | None = None, creates: Sequence[FileWrite] = ()) -> None:
    """Print the headers and each change's description (path, text) sorted by path, the realigned baseline included,
    then write them with `--apply`, `creates` after the moves, listing each changed path once; `BaselineFailed` when
    the checker fails."""
    if baseline_runs(root):
        progress.phase("baseline")
    with timed("baseline"):
        aligned = align(root, writes, moves, edits=edits, moved_code=moved_code)
    described = list(described)
    if aligned is not None:
        for warning in aligned.warnings:
            print(warning, file=sys.stderr)
    if aligned is not None and aligned.write is not None:
        described.append((aligned.write.rel, aligned.description))
        writes = [*writes, aligned.write]
    ordered = sorted(described)
    if apply_:
        progress.phase("write")
        with timed("write"):
            verify(root.resolve(), writes)
    print("\n".join(headers) + "\n\n\n" + "".join(text + "\n" for _, text in ordered))
    touched = list(dict.fromkeys(path for path, _ in ordered))
    if apply_:
        with timed("write"):
            apply(root.resolve(), writes, moves, creates)
        print(message("refactor.applied", count=len(touched)))
        for p in touched:
            print(message("refactor.applied-file", path=p))
    else:
        print(message("refactor.dry-run", count=len(touched)))


def run_map(root: Path, entries: list[MapEntry], options: RenameOptions, *, apply_: bool, map_shown: str,
            progress: Progress) -> int:
    """0 when computed (and written with `--apply`); `Refused` with every refusal when it refuses."""
    engine = RenameMap(root, entries, options, map_shown, progress)
    try:
        return engine.run(apply_)
    except LanguageServerError as exc:
        engine.server.close()
        raise Refused([server_failed(exc)]) from None
    except ConfigError as exc:
        raise Refused([refusal(str(exc))]) from None
    finally:
        engine.server.close()


def entry_options(options: dict[str, Any]) -> RenameOptions:
    return RenameOptions(
        in_hierarchy=bool(options.get("in_hierarchy", True)),
        unsure=options.get("unsure") == "include",
        allow_blindspots=bool(options.get("allow_blindspots")),
        with_sites=tuple(options.get("with_stand_ins") or ()),
        without_sites=tuple(options.get("without_stand_ins") or ()),
        keep=tuple(options.get("keep") or ()),
        docs=bool(options.get("docs")),
        fail_fast=bool(options.get("fail_fast")),
        stub=options.get("stub"),
    )
