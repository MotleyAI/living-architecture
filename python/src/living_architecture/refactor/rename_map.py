"""`dr-refactor rename-map`: rename and retarget entries resolved against the code before the map, checked before
any reference search, computed on one snapshot and one occurrence index (one language server, started only when
needed), printed as one diff and written all or nothing. `rename` and `retarget` are one-entry maps."""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from rope.base.change import ChangeContents, ChangeSet, MoveResource
from rope.base.fscommands import unicode_to_file_data
from rope.base.project import Project
from rope.base.resources import File

from living_architecture.config import ConfigError, source_files
from living_architecture.contract import manifest, message
from living_architecture.lang import LanguageServerError
from living_architecture.refactor.baseline_align import (
    BaselineFailed,
    align,
    baseline_runs,
    config_error,
    probe,
)
from living_architecture.refactor.bindings import BindingCheck, EntryEdits, first_conflict
from living_architecture.refactor.diff_render import edit_description
from living_architecture.refactor.entry_location import Entry, EntryLocator
from living_architecture.refactor.index_cache import IndexCache
from living_architecture.refactor.keyed import TypeFacts, UnresolvedBase
from living_architecture.refactor.literal_rename import LiteralRename, check_value, literal_member_at
from living_architecture.refactor.locators import RefactorError, project_rel, resolve
from living_architecture.refactor.map_file import MapEntry, MapError
from living_architecture.refactor.member_namespace import Hierarchy, MemberCheck, RenamedMember
from living_architecture.refactor.member_scan import probe_round
from living_architecture.refactor.move_edits import NameConflict
from living_architecture.refactor.occurrence_index import RunIndex, ServerSession, candidate_files
from living_architecture.refactor.outcomes import Finding
from living_architecture.refactor.position_map import Edit
from living_architecture.refactor.progress import Progress, Refusal, Refused, checker_cause, refusal, unique
from living_architecture.refactor.python_project import Snapshot
from living_architecture.refactor.python_source import SourceFile
from living_architecture.refactor.rename_union import (
    RenameOptions,
    Session,
    SymbolRename,
)
from living_architecture.refactor.retarget import (
    AliasRetarget,
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
from living_architecture.refactor.sites import Keeps, Site, keep_spells
from living_architecture.refactor.symbol_path import LocatorError, declaration_scope, locate
from living_architecture.refactor.text_edits import TextEdit, apply_edits, merge_edits
from living_architecture.refactor.timings import timed
from living_architecture.refactor.writer import FileChanged, FileMove, FileWrite, apply, verify

_WORD = re.compile(r"\w+")
_CANNOT_RENAME = "refactor.cannot-rename"


Renaming = SymbolRename | LiteralRename


class _Resolved:
    """An entry located: its file, what it names, its canonical symbol and its intent, and every map index merged
    into it."""

    def __init__(self, entry: MapEntry, rel: str, located: Entry | None, key: tuple[object, ...],
                 literal: ast.Constant | None = None, offset: int = 0) -> None:
        self.entry = entry
        self.indexes = [entry.index]
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


def site_checks(sites: list[tuple[str, str, Path]], root: Path) -> tuple[list[Refusal], set[tuple[str, str]]]:
    """`refactor.site-missing` for each (option, raw, base) site naming nothing; the missing ones."""
    out: list[Refusal] = []
    missing: set[tuple[str, str]] = set()
    for option, raw, base in sites:
        if Site.parse(raw, root, base).missing(root):
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
                moved: list[str], skipped: set[tuple[str, str]], data: Callable[[str], bytes] | None = None) -> list[Refusal]:
    """`refactor.keep-unmatched` for each keep covering no line spelling one of `names` and no moved file."""
    out: list[Refusal] = []
    for raw in keeps:
        if ("--keep", raw) in skipped:
            continue
        if not keep_spells(Site.parse(raw, root), editable, text, names, moved, data):
            out.append(refusal(message("refactor.keep-unmatched", site=raw), 2))
    return out


def _spelled(entry: MapEntry) -> str | None:
    """The name an entry's locator spells: the last word of its symbol path."""
    words = _WORD.findall(entry.locator.symbol or "")
    return words[-1] if words else None


class RenameMap:
    """The entries of a map computed as one refactor."""

    def __init__(self, root: Path, entries: list[MapEntry], options: RenameOptions, map_shown: str,
                 progress: Progress) -> None:
        self.entries = entries
        self.options = options
        self.map_shown = map_shown
        self.progress = progress
        self.session = Session(root)
        self.root = self.session.root
        self.server = ServerSession(self.root, self.session.read)
        self.index = RunIndex(self.root, self.session.load, self.server, IndexCache(self.root))
        self.locator = EntryLocator(self.root, self._definitions, self.session.snapshot, self.session.layout)
        self.stopped = False

    # ---- resolve

    def _locate(self, entry: MapEntry) -> tuple[str, int]:
        rel = project_rel(self.root, entry.path)
        offset, _ = resolve(entry.locator, self.session.snapshot.source(rel), entry.path)
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
            raise RefactorError(message(_CANNOT_RENAME))
        check_value(entry.new_name)
        return _Resolved(entry, rel, None, ("literal", rel, source.span(node)[0]), literal=node)

    def _resolve(self, entry: MapEntry) -> _Resolved:
        located = self._locate(entry)
        literal = self._literal(entry, *located)
        if literal is not None:
            return literal
        found = self.locator.at(*located)
        resolved = _Resolved(entry, located[0], found, found.key, offset=located[1])
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
                found = failure(exc, self.root)
                assert found is not None
                failures.append(found)
                spelled = spelled and _spelled(entry) is not None
                continue
            first = next((r for r in out if r.key == resolved.key), None)
            if first is None:
                out.append(resolved)
            elif first.intent() != resolved.intent():
                failures.append(refusal(message("refactor.map-duplicate", map=self.map_shown, first=first.entry.index,
                                                second=entry.index), 2))
            else:
                first.indexes.append(entry.index)
        if len(out) > 1 and any(r.is_module() for r in out):
            failures.append(refusal(message(_CANNOT_RENAME)))
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
        sites = [("--with", raw, self.root) for raw in options.with_sites]
        sites += [("--without", raw, self.root) for raw in options.without_sites]
        sites += [("--keep", raw, Path.cwd()) for raw in options.keep]
        found, missing = site_checks(sites, self.root)
        names = self.names(resolved)
        text = self.session.snapshot.text
        if spelled and options.keep and not any(r.literal is not None for r in resolved):
            editable = editable_files(self.root, options.docs)
            found += keep_checks(list(options.keep), self.root, editable, text, names, self._moved(resolved), missing,
                                 self.session.snapshot.data)
        if not resolved or not self._cached(resolved):
            try:
                self.server.get()
            except LanguageServerError as exc:
                found.append(server_failed(exc))
        source = self.root / resolved[0].rel if resolved else Path(self.entries[0].path)
        return found + baseline_probe(self.root, source)

    def _cached(self, resolved: list[_Resolved]) -> bool:
        """Fix the run's export request; whether the run can do without a language server: a module rename, or
        symbol renames whose export is cached, with no `Literal` member."""
        if any(r.is_module() for r in resolved):
            return True
        names = {r.old() for r in resolved if r.literal is None}
        news = {str(r.entry.new_name) for r in resolved if r.literal is None and r.entry.new_name is not None}
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
            if r.literal is not None:
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
            if r.new == r.old:
                continue
            try:
                r.prepare(self.index)
            except _ENTRY_ERRORS as exc:
                failed[n - 1] = [found] if (found := failure(exc, self.root)) is not None else []
                self.stopped = self.options.fail_fast
        return failed

    def seed(self, renames: list[Renaming], active: list[int], failed: dict[int, list[Refusal]]) -> TypeFacts:
        facts = TypeFacts(self.index, self.session.load)
        for i in active:
            try:
                renames[i].seed(facts)
            except UnresolvedBase as exc:
                failed[i] = [found] if (found := failure(exc, self.root)) is not None else []
        live = [i for i in active if i not in failed]
        renamed = {site for i in live for site in renames[i].seeds}
        for i in live:
            renames[i].is_renamed = renamed.__contains__
        symbols = sorted({renames[i].old for i in live if isinstance(renames[i], SymbolRename)})
        if symbols:
            files = [(self.root / rel, self.session.snapshot.source(rel)) for rel in sorted(
                {rel for i in live if isinstance(renames[i], SymbolRename) for rel in renames[i].candidates})]
            with timed("rules"):
                probe_round(self.index, files, symbols, self.session.load)
        return facts

    # ---- rules

    def _group_refusals(self, group: list[int], renames: list[Renaming], failed: dict[int, list[Refusal]]) -> list[Refusal]:
        own = [f for i in group for f in failed.get(i, [])]
        live = [renames[i] for i in group if i not in failed]
        retargets = [f for r in live if isinstance(r, AliasRetarget) for f in r.refusals]
        blind = [] if self.options.allow_blindspots else [b for r in live for b in r.blindspots]
        stand_ins = [s for r in live for s in r.stand_in_findings()]
        return unique([*own, *_texts(_unique([*retargets, *blind, *stand_ins]))])

    def rules(self, renames: list[Renaming], resolved: list[_Resolved], failed: dict[int, list[Refusal]],
              facts: TypeFacts, keeps: Keeps) -> list[list[TextEdit]]:
        """Each old-name group's rules, in the order of its first entry, its line printed as it is done; the edits
        each rename's keeps dropped."""
        self.progress.phase("rules")
        groups: dict[str, list[int]] = {}
        for i, r in enumerate(renames):
            groups.setdefault(r.old, []).append(i)
        olds = {r.old for r in renames if r.new != r.old}
        dropped: list[list[TextEdit]] = [[] for _ in renames]
        for n, (old, group) in enumerate(groups.items(), 1):
            live = [i for i in group if renames[i].new != old]
            self._group_rules(live, renames, failed, facts)
            for i in live:
                if i not in failed:
                    dropped[i] = self._finish(renames[i], olds, keeps)
            refused = self._group_refusals(group, renames, failed)
            indexes = sorted(index for i in group for index in resolved[i].indexes)
            news = ", ".join(dict.fromkeys(renames[i].new for i in group))
            self.progress.result(n, len(groups), indexes, old, news, [line for f in refused for line in f.lines])
            if refused and self.options.fail_fast:
                self.stopped = True
                break
        if not self.stopped:
            self._imports([r for i, r in enumerate(renames) if i not in failed])
        return dropped

    def _group_rules(self, group: list[int], renames: list[Renaming], failed: dict[int, list[Refusal]],
                     facts: TypeFacts) -> None:
        for i in group:
            if i in failed:
                continue
            try:
                renames[i].rules(self.index, facts)
            except _ENTRY_ERRORS as exc:
                failed[i] = [found] if (found := failure(exc, self.root)) is not None else []
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

    def _imports(self, renames: list[Renaming]) -> None:
        """The imports every retarget's sites need, planned once."""
        retargets = [r for r in renames if isinstance(r, AliasRetarget)]
        if not retargets:
            return
        with timed("rules"):
            planned = plan_imports(self.session, [n for r in retargets for n in r.needs])
        by_entry = {r.index: r for r in retargets}
        for entry, edit in planned:
            by_entry[entry].imports.append(edit)
        for r in retargets:
            r.edits += r.imports

    def _keep(self, r: Renaming, keeps: Keeps) -> list[TextEdit]:
        """Drop every edit, blind spot and leftover of `r` at a kept site (a retarget's are dropped already); the
        dropped edits."""
        snapshot = self.session.snapshot
        kept = [not isinstance(r, AliasRetarget) and keeps.kept(e.path, snapshot.source(e.path).line(e.start))
                for e in r.edits]
        held = r.held if isinstance(r, AliasRetarget) else []
        dropped = [*held, *(e for e, k in zip(r.edits, kept, strict=True) if k)]
        r.edits = [e for e, k in zip(r.edits, kept, strict=True) if not k]
        r.blindspots = [b for b in r.blindspots if not keeps.kept(b.path, b.line)]
        r.leftovers = [f for f in r.leftovers if not keeps.kept(f.path, f.line, mark=False)]
        if isinstance(r, SymbolRename):
            r.unresolved = [f for f in r.unresolved if not keeps.kept(f.path, f.line)]
        return dropped

    # ---- the final report

    def merged(self, renames: list[Renaming], indexes: list[int]) -> tuple[list[TextEdit], list[Refusal]]:
        """Every entry's edits, identical ones merged; a `refactor.map-conflict` for each site two entries rewrite
        differently."""
        tagged = sorted(
            {(e, i) for r, i in zip(renames, indexes, strict=True) for e in r.edits},
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

    def check_names(self, renames: list[Renaming], resolved: list[_Resolved], dropped: list[list[TextEdit]], *,
                    together: bool) -> list[NameConflict]:
        """The first site of each name-conflict check that finds one: each `new_name` entry alone against the code
        before the map, in map order, then, when `together`, every entry together."""
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
        rels = self.session.python_files()
        bindings = BindingCheck(rels, self.session.source_folders(), self.session.snapshot.source)
        namespace = MemberCheck(Hierarchy(self.root, rels, self.session.snapshot.source, self.index), self.session.snapshot.text)
        passes = [[e] for e, res in zip(entries, resolved, strict=True) if res.entry.new_name is not None]
        out: list[NameConflict] = []
        for group in passes if passes == [entries] or not together else [*passes, entries]:
            renamed = [m for e, m in members if any(e is g for g in group)]
            found = first_conflict(
                bindings.conflicts(group) + namespace.conflicts(renamed, {m.site for m in renamed}),
                self.session.snapshot.source,
            )
            if found is not None:
                out.append(found)
        return out

    def keyed_conflicts(self, renames: list[Renaming]) -> list[NameConflict]:
        """Each rename's first renamed keyword or key meeting its new name."""
        out: list[NameConflict] = []
        for r in renames:
            try:
                r.check_conflicts(r.edits)
            except NameConflict as conflict:
                out.append(conflict)
        return out

    def site_findings(self, renames: list[Renaming], keeps: Keeps) -> list[Refusal]:
        """Each `--with` or `--without` site no member entry's stand-ins hold, then each keep that matched nothing."""
        matched = {raw for r in renames if r.member for raw in r.matched_sites}
        out = [refusal(message("refactor.not-stand-in", site=raw), 2)
               for raw in (*self.options.with_sites, *self.options.without_sites) if raw not in matched]
        return out + [refusal(message("refactor.keep-unmatched", site=raw), 2) for raw in keeps.unmatched()]

    def report(self, renames: list[Renaming], resolved: list[_Resolved], failed: dict[int, list[Refusal]],
               dropped: list[list[TextEdit]], keeps: Keeps) -> tuple[list[TextEdit], list[Refusal]]:
        """The merged edits and the final report: entry failures, retarget refusals, blind spots, stand-ins, name
        conflicts and map conflicts, then the site findings (none on a partial computation), then the blind-spot
        count."""
        live = [r for i, r in enumerate(renames) if i not in failed]
        own = [f for i in sorted(failed) for f in failed[i]]
        retargets = _texts(_unique(f for r in live if isinstance(r, AliasRetarget) for f in r.refusals))
        blindspots = _unique(b for r in live for b in r.blindspots)
        blind = [] if self.options.allow_blindspots else blindspots
        stand_ins = _texts(_unique(s for r in live for s in r.stand_in_findings()))
        edits: list[TextEdit] = []
        conflicts: list[Refusal] = []
        sites: list[Refusal] = []
        if not self.stopped:
            self.progress.phase("conflicts")
            with timed("conflicts"):
                edits, merged = self.merged(renames, [r.entry.index for r in resolved])
                checked = self.check_names(renames, resolved, dropped, together=not merged)
                keyed = self.keyed_conflicts(live)
            names = sorted({(c.path, c.line, c.name): c for c in [*keyed, *checked]}.items())
            conflicts = [*(_name_conflict(c) for _, c in names), *merged]
            sites = [] if failed else self.site_findings(live, keeps)
        attrs = ", .".join(dict.fromkeys(r.old for r in live if r.blindspots))
        closing = [refusal(message("refactor.blindspots", count=len(blind), attr=attrs))] if blind else []
        return edits, unique([*own, *retargets, *_texts(blind), *stand_ins, *conflicts, *sites, *closing])

    def findings(self, renames: list[Renaming], edits: list[TextEdit], listed: list[Finding]) -> list[Finding]:
        """The blind spots let through, then the leftovers no entry's `edits` rewrite with the `listed` files, sorted."""
        blindspots = _unique(b for r in renames for b in r.blindspots)
        by_path: dict[str, list[TextEdit]] = {}
        for e in edits:
            by_path.setdefault(e.path, []).append(e)
        unique_ = {(f.path, f.line, f.col, f.text): f for r in renames for f in r.leftovers
                   if not any(f.covers(e) for e in by_path.get(f.path, ()))}
        unique_ |= {(f.path, f.line, f.col, f.text): f for f in listed}
        unique_ |= {(f.path, f.line, f.col, f.text): f for r in renames if isinstance(r, SymbolRename) for f in r.unresolved}
        leftovers = [unique_[k] for k in sorted(unique_)]
        return [*blindspots, *leftovers]

    def outputs(self, edits: list[TextEdit]) -> tuple[list[tuple[str, str]], list[FileWrite]]:
        """Each changed file's printed diff, and the writes."""
        return changes_of(self.session.snapshot, edits)

    # ---- the run

    def run(self, apply_: bool, module_rename: Callable[[RenameMap, _Resolved], int]) -> int:
        try:
            self.progress.phase("resolve")
            with timed("resolve"):
                resolved, failures, spelled = self.resolve()
            self.progress.phase("checks")
            failures += self.checks(resolved, spelled)
            if failures:
                raise Refused(failures)
            self.progress.phase("references")
            if resolved[0].is_module():
                self.server.close()
                return module_rename(self, resolved[0])
            renames = self.build(resolved)
            failed = self.references(renames, resolved)
            active = [i for i, r in enumerate(renames) if r.new != r.old and i not in failed]
            keeps = Keeps(self.options.keep, self.root)
            dropped: list[list[TextEdit]] = [[] for _ in renames]
            if not self.stopped:
                facts = self.seed(renames, active, failed)
                dropped = self.rules(renames, resolved, failed, facts, keeps)
        finally:
            self.server.close()
            self.index.close()
        olds = [r.old for r in renames if r.new != r.old]
        listed = undecodable(self.session.snapshot, self.session.all_python_files(), olds, keeps)
        edits, refusals = self.report(renames, resolved, failed, dropped, keeps)
        if refusals:
            raise Refused(refusals)
        if self.options.unsure:
            print(message("refactor.unsure-warning"))
        for finding in self.findings(renames, edits, listed):
            print(finding.text, file=sys.stderr)
        described, writes = self.outputs(edits)
        by_file: dict[str, list[Edit]] = {}
        for e in edits:
            by_file.setdefault(e.path, []).append((e.start, e.end, len(e.new_text)))
        emit(self.root, [r.header() for r in renames], described, apply_, writes, [], self.progress, edits=by_file)
        return 0


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
         edits: dict[str, list[Edit]] | None = None) -> None:
    """Print the headers and each change's description (path, text) sorted by path, the realigned baseline included,
    then write them with `--apply`; `BaselineFailed` when the checker fails."""
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
    touched = [path for path, _ in ordered]
    if apply_:
        with timed("write"):
            apply(root.resolve(), writes, moves)
        print(message("refactor.applied", count=len(touched)))
        for p in touched:
            print(message("refactor.applied-file", path=p))
    else:
        print(message("refactor.dry-run", count=len(touched)))


def run_map(root: Path, entries: list[MapEntry], options: RenameOptions, *, apply_: bool, map_shown: str,
            progress: Progress, module_rename: Callable[[RenameMap, _Resolved], int]) -> int:
    """0 when computed (and written with `--apply`); `Refused` with every refusal when it refuses."""
    engine = RenameMap(root, entries, options, map_shown, progress)
    try:
        return engine.run(apply_, module_rename)
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
    )
