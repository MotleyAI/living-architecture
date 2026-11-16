"""`dr-refactor`: IDE-grade Python refactors via rope (rename, rename-map, retarget, move-symbol, move-module)."""

from __future__ import annotations

import difflib
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from rope.base.change import ChangeContents, ChangeSet
from rope.base.exceptions import BadIdentifierError, RefactoringError
from rope.base.project import Project
from rope.base.resources import File, Resource
from rope.refactor.move import MoveGlobal, MoveModule, create_move
from rope.refactor.rename import Rename

from living_architecture.contract import message
from living_architecture.refactor.baseline_align import BaselineFailed
from living_architecture.refactor.bindings import BindingCheck, EntryEdits, first_conflict, module_binding
from living_architecture.refactor.locators import (
    Locator,
    RefactorError,
    offset_from_line_col,
    resolve,
    resource,
)
from living_architecture.refactor.map_file import MapEntry, MapError, load_map
from living_architecture.refactor.move_edits import NameConflict, module_move_changes, symbol_move_changes
from living_architecture.refactor.progress import Progress, Refusal, Refused, refusal
from living_architecture.refactor.python_source import nfkc, split_lines
from living_architecture.refactor.rename_map import (
    baseline_failed,
    baseline_probe,
    change_set_writes,
    emit,
    entry_options,
    run_map,
    source_bytes,
    walker_gaps,
)
from living_architecture.refactor.rename_union import RenameOptions, Snapshot
from living_architecture.refactor.rope_patches import WalkerGap, apply_rope_patches
from living_architecture.refactor.routing import language_files
from living_architecture.refactor.sites import Keeps
from living_architecture.refactor.symbol_path import LocatorError
from living_architecture.refactor.text_edits import TextEdit, diff_edits
from living_architecture.refactor.timings import timed
from living_architecture.refactor.writer import FileChanged, WriteFailed

apply_rope_patches()

__all__ = ["Locator", "RefactorError", "run_refactor"]

_offset_from_line_col = offset_from_line_col


def _destination(project: Project, dest: str, *, folder: bool) -> Resource:
    """`--dest` as an existing directory (`folder`) or file in the project."""
    resolved = Path(dest).resolve()
    if resolved.is_relative_to(Path(project.address).resolve()) and not (
        resolved.is_dir() if folder else resolved.is_file()
    ):
        raise RefactorError(message("refactor.destination-missing", path=dest))
    return resource(project, dest)


def _emit(project: Project, changes: ChangeSet, apply: bool, before: dict[str, bytes], progress: Progress, *,
          moved_code: bool = False) -> None:
    """Print a rope change set sorted by path; write it all or nothing with `apply`, refusing a file that changed
    since `before` was read."""
    writes, moves = change_set_writes(changes, before)
    emit(project, [f"{changes}:"], changes, apply, writes, moves, progress, moved_code=moved_code)


def _kept(project: Project, changes: ChangeSet, keep: tuple[str, ...]) -> tuple[ChangeSet, list[str]]:
    """`changes` without what touches a `--keep` site: a kept file's move or edits, a kept line's edits; and every
    keep that matches neither."""
    if not keep:
        return changes, []
    keeps = Keeps(keep, Path(project.address).resolve())

    def kept(rel: str, line: int | None) -> bool:
        return keeps.kept(rel, line)

    out = ChangeSet(changes.description)
    for change in changes.changes:
        if isinstance(change, ChangeContents):
            old = change.resource.read()
            new = _kept_lines(change.resource.path, old, change.new_contents, kept)
            if new != old:
                out.add_change(ChangeContents(change.resource, new))
        elif not kept(change.resource.path, None):
            out.add_change(change)
    return out, keeps.unmatched()


def _kept_lines(rel: str, old: str, new: str, kept: Callable[[str, int | None], bool]) -> str:
    """`new` with each changed block that holds a kept line of `old` restored."""
    old_lines, new_lines = split_lines(old), split_lines(new)
    out: list[str] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_opcodes():
        if tag == "equal":
            out += old_lines[i1:i2]
        elif tag == "replace" and i2 - i1 == j2 - j1:
            out += [old_lines[i1 + k] if kept(rel, i1 + k + 1) else new_lines[j1 + k] for k in range(i2 - i1)]
        else:
            # Every line is checked, so each keep covering the block counts as matched.
            hits = sum(kept(rel, n) for n in range(i1 + 1, max(i2, i1 + 1) + 1))
            out += old_lines[i1:i2] if hits else new_lines[j1:j2]
    return "".join(out)


def _taken(module: Resource, new_name: str, snapshot: Snapshot, rels: list[str]) -> NameConflict | None:
    """The finding when the renamed module's package already binds `new_name`: a module, a package (its
    `__init__.py`, else its first Python file) or a binding of its `__init__.py`."""
    parent = module.parent.path
    base = f"{parent}/{nfkc(new_name)}" if parent else nfkc(new_name)
    if f"{base}.py" in rels:
        return NameConflict(new_name, f"{base}.py", 1)
    inside = sorted(rel for rel in rels if rel.startswith(base + "/"))
    if inside:
        init = f"{base}/__init__.py"
        return NameConflict(new_name, init if init in inside else inside[0], 1)
    init = f"{parent}/__init__.py" if parent else "__init__.py"
    offset = module_binding(snapshot.text(init), new_name) if init in rels else None
    return None if offset is None else NameConflict(new_name, init, snapshot.source(init).line(offset))


def _edits(changes: ChangeSet, before: dict[str, bytes], snapshot: Snapshot) -> tuple[list[TextEdit], dict[str, str]]:
    """A rope change set as edits over the snapshot's texts, and its moves (a file to its new path)."""
    writes, moves = change_set_writes(changes, before)
    edits = [e for w in writes for e in diff_edits(w.rel, snapshot.text(w.rel), snapshot.decode(w.rel, w.new))]
    moved: dict[str, str] = {}
    for move in moves:
        for rel in before:
            if rel == move.rel or rel.startswith(move.rel + "/"):
                moved[rel] = move.dest + rel[len(move.rel) :]
    return edits, moved


def _module_rename(project: Project, renamer: Rename, entry: MapEntry, options: RenameOptions, apply: bool,
                   progress: Progress) -> int:
    """rope's rename of a module, its `--keep` sites left; refused when the new name is taken, rope's edits change
    what a name means, or a site matches nothing it must."""
    if entry.new_name is None:
        raise RefactorError(message("refactor.cannot-rename"))
    before = source_bytes(project)
    root = Path(project.address).resolve()
    snapshot = Snapshot(root)
    rels = [p.relative_to(root).as_posix() for p in language_files(root, "python")]
    pyobject = renamer.old_pyname.get_object() if renamer.old_pyname is not None else None
    module = pyobject.get_resource() if pyobject is not None else None
    with timed("resolve"):
        taken = _taken(module, entry.new_name, snapshot, rels) if module is not None else None
    found: NameConflict | None = taken if renamer.get_old_name() != entry.new_name else None
    kept, unmatched = ChangeSet(""), list(options.keep)
    if found is None:
        try:
            with timed("references"):
                changes = renamer.get_changes(
                    entry.new_name, in_hierarchy=options.in_hierarchy, unsure=(lambda *_: True) if options.unsure else None
                )
        except (RefactoringError, BadIdentifierError):
            raise RefactorError(message("refactor.cannot-rename")) from None
        kept, unmatched = _kept(project, changes, options.keep)
        with timed("resolve"):
            every, _ = _edits(changes, before, snapshot)
            written, moves = _edits(kept, before, snapshot)
            folders = sorted({"", *(f.path for f in project.get_source_folders())})
            found = first_conflict(BindingCheck(rels, folders, snapshot.source).conflicts(
                [EntryEdits(index=1, new_name=entry.new_name, edits=written, kept=[e for e in every if e not in written])],
                moves), snapshot.source)
    refusals: list[Refusal] = []
    if found is not None:
        refusals.append(refusal(message("refactor.name-conflict", name=found.name, path=found.path, line=found.line)))
    refusals += [refusal(message("refactor.not-stand-in", site=raw), 2) for raw in (*options.with_sites, *options.without_sites)]
    refusals += [refusal(message("refactor.keep-unmatched", site=raw), 2) for raw in unmatched]
    if refusals:
        raise Refused(refusals)
    _emit(project, kept, apply, before, progress)
    return 0


def _checks(project: Project, progress: Progress, failures: list[Refusal], names: set[str], source: Path) -> None:
    """The `checks` phase of a move: walker gaps in the files spelling `names`, the checker; `Refused` with them
    and the resolution `failures`."""
    progress.phase("checks")
    root = Path(project.address).resolve()
    failures = [*failures, *walker_gaps(root, Snapshot(root).text, names), *baseline_probe(root, source)]
    if failures:
        raise Refused(failures)
    progress.phase("references")


def _first_source(path: Path) -> Path:
    """`path`, or the first Python file under the directory."""
    if not path.is_dir():
        return path
    return next(iter(language_files(path, "python")), path)


def move_symbol(project: Project, *, file: str, locator: Locator, dest: str, apply: bool, progress: Progress) -> None:
    before = source_bytes(project)
    progress.phase("resolve")
    failures: list[Refusal] = []
    mover: MoveGlobal | None = None
    target: File | None = None
    try:
        with timed("resolve"):
            offset, located = resolve(locator, file)
            if located is not None and not located.top_level:
                raise RefactorError(message("refactor.not-movable", path=file))
            mover = cast(MoveGlobal, create_move(project, resource(project, file), offset))
            target = cast(File, _destination(project, dest, folder=False))
    except LocatorError as exc:
        failures.append(refusal(str(exc), 2))
    except RefactorError as exc:
        failures.append(refusal(str(exc)))
    _checks(project, progress, failures, {mover.old_name} if mover is not None else set(), Path(file))
    assert mover is not None and target is not None
    if target == mover.source:
        _emit(project, ChangeSet(f"Moving global <{mover.old_name}>"), apply, before, progress)
        return
    with timed("references"):
        changes = symbol_move_changes(project, mover, target)
    _emit(project, changes, apply, before, progress, moved_code=True)


def move_module(project: Project, *, module: str, dest: str, apply: bool, progress: Progress) -> None:
    before = source_bytes(project)
    progress.phase("resolve")
    failures: list[Refusal] = []
    mover: MoveModule | None = None
    dest_folder: Resource | None = None
    try:
        with timed("resolve"):
            mover = cast(MoveModule, create_move(project, resource(project, module)))
            dest_folder = _destination(project, dest, folder=True)
    except RefactorError as exc:
        failures.append(refusal(str(exc)))
    name = Path(module).stem if not Path(module).is_dir() else Path(module).name
    _checks(project, progress, failures, {name}, _first_source(Path(module)))
    assert mover is not None and dest_folder is not None
    with timed("references"):
        changes = module_move_changes(project, mover, dest_folder)
    _emit(project, changes, apply, before, progress)


def _renamer(renamer: Rename | None) -> Rename:
    assert renamer is not None
    return renamer


def _locator(options: dict[str, Any]) -> Locator:
    return Locator(offset=options.get("offset"), line=options.get("line"), col=options.get("col"),
                   symbol=options.get("symbol"))


def _entries(command: str, project_root: str, options: dict[str, Any]) -> tuple[list[MapEntry], str]:
    """The map a `rename`, `retarget` or `rename-map` runs, and the map as named in findings."""
    if command == "rename-map":
        return load_map(str(options["map"]), project_root), str(options["map"])
    file = str(options["file"])
    intent = {"new_name": str(options["new_name"])} if command == "rename" else {"retarget": str(options["target"])}
    return [MapEntry(index=1, file=file, path=file, locator=_locator(options), **intent)], ""


def _run(project: Project, project_root: str, command: str, apply: bool, options: dict[str, Any]) -> int:
    progress = Progress()
    if command in ("rename", "retarget", "rename-map"):
        entries, shown = _entries(command, project_root, options)
        rename_options = entry_options(options)
        return run_map(
            project, entries, rename_options, apply_=apply, map_shown=shown, progress=progress,
            module_rename=lambda r: _module_rename(project, _renamer(r.renamer), r.entry, rename_options, apply, progress),
        )
    if command == "move-symbol":
        move_symbol(project, file=str(options["file"]), locator=_locator(options), dest=str(options["dest"]), apply=apply,
                    progress=progress)
    else:
        move_module(project, module=str(options["module"]), dest=str(options["dest"]), apply=apply, progress=progress)
    return 0


def run_refactor(*, project_root: str, command: str, apply: bool, options: dict[str, Any]) -> int:
    """`dr-refactor` handler: 0 on success, else the highest exit code of the refusals on stderr: 1 when the refactor
    cannot proceed or refuses, 2 for a locator or map error, or a `--keep`, `--with` or `--without` site that matches
    nothing it must."""
    # rope documents `ropefolder=None` (no rope folder); its signature infers `str` from the default.
    with timed("load"):
        project = Project(str(Path(project_root).resolve()), ropefolder=None)  # pyright: ignore[reportArgumentType]
    try:
        return _run(project, project_root, command, apply, options)
    except (LocatorError, MapError) as exc:
        print(exc, file=sys.stderr)
        return 2
    except Refused as exc:
        print("\n".join(exc.lines), file=sys.stderr)
        return exc.code
    except RefactorError as exc:
        print(exc, file=sys.stderr)
        return 1
    except WalkerGap as gap:
        print(message("refactor.rope-walk", path=gap.path, line=gap.line), file=sys.stderr)
        return 1
    except FileChanged as changed:
        print(message("refactor.file-changed", path=changed.path), file=sys.stderr)
        return 1
    except BaselineFailed as exc:
        print("\n".join(baseline_failed(exc).lines), file=sys.stderr)
        return 1
    except WriteFailed as failed:
        if failed.unrestored:
            print(message("refactor.rollback-failed", path=failed.path, paths=", ".join(failed.unrestored)), file=sys.stderr)
        else:
            print(message("refactor.write-failed", path=failed.path), file=sys.stderr)
        return 1
    except NameConflict as conflict:
        print(message("refactor.name-conflict", name=conflict.name, path=conflict.path, line=conflict.line), file=sys.stderr)
        return 1
    finally:
        project.close()
