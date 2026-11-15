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
from living_architecture.refactor.python_source import split_lines
from living_architecture.refactor.rename_map import (
    MapConflict,
    Refused,
    change_set_writes,
    emit,
    entry_options,
    run_map,
    source_bytes,
)
from living_architecture.refactor.rename_union import RenameOptions, Snapshot
from living_architecture.refactor.rope_patches import WalkerGap, apply_rope_patches
from living_architecture.refactor.routing import language_files
from living_architecture.refactor.sites import Keeps, SiteError
from living_architecture.refactor.symbol_path import LocatorError
from living_architecture.refactor.text_edits import TextEdit, diff_edits
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


def _emit(project: Project, changes: ChangeSet, apply: bool, before: dict[str, bytes], *, moved_code: bool = False) -> None:
    """Print a rope change set sorted by path; write it all or nothing with `apply`, refusing a file that changed
    since `before` was read."""
    writes, moves = change_set_writes(changes, before)
    emit(project, [f"{changes}:"], changes, apply, writes, moves, moved_code=moved_code)


def _kept(project: Project, changes: ChangeSet, keep: tuple[str, ...]) -> ChangeSet:
    """`changes` without what touches a `--keep` site: a kept file's move or edits, a kept line's edits; `SiteError`
    for a keep that matches neither."""
    if not keep:
        return changes
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
    keeps.check()
    return out


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
    base = f"{parent}/{new_name}" if parent else new_name
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


def _module_rename(project: Project, renamer: Rename, entry: MapEntry, options: RenameOptions, apply: bool) -> int:
    """rope's rename of a module, its `--keep` sites left; `NameConflict` when the new name is taken or rope's edits
    change what a name means."""
    if entry.new_name is None:
        raise RefactorError(message("refactor.cannot-rename"))
    if options.with_sites or options.without_sites:
        raise SiteError("refactor.not-stand-in", (*options.with_sites, *options.without_sites)[0])
    before = source_bytes(project)
    root = Path(project.address).resolve()
    snapshot = Snapshot(root)
    rels = [p.relative_to(root).as_posix() for p in language_files(root, "python")]
    pyobject = renamer.old_pyname.get_object() if renamer.old_pyname is not None else None
    module = pyobject.get_resource() if pyobject is not None else None
    taken = _taken(module, entry.new_name, snapshot, rels) if module is not None else None
    if taken is not None and renamer.get_old_name() != entry.new_name:
        raise taken
    try:
        changes = renamer.get_changes(
            entry.new_name, in_hierarchy=options.in_hierarchy, unsure=(lambda *_: True) if options.unsure else None
        )
    except (RefactoringError, BadIdentifierError):
        raise RefactorError(message("refactor.cannot-rename")) from None
    kept = _kept(project, changes, options.keep)
    every, _ = _edits(changes, before, snapshot)
    written, moves = _edits(kept, before, snapshot)
    folders = sorted({"", *(f.path for f in project.get_source_folders())})
    found = first_conflict(BindingCheck(rels, folders, snapshot.source).conflicts(
        [EntryEdits(index=1, new_name=entry.new_name, edits=written, kept=[e for e in every if e not in written])],
        moves), snapshot.source)
    if found is not None:
        raise found
    _emit(project, kept, apply, before)
    return 0


def move_symbol(project: Project, *, file: str, locator: Locator, dest: str, apply: bool) -> None:
    before = source_bytes(project)
    offset, located = resolve(locator, file)
    if located is not None and not located.top_level:
        raise RefactorError(message("refactor.not-movable", path=file))
    mover = cast(MoveGlobal, create_move(project, resource(project, file), offset))
    target = cast(File, _destination(project, dest, folder=False))
    if target == mover.source:
        _emit(project, ChangeSet(f"Moving global <{mover.old_name}>"), apply, before)
        return
    _emit(project, symbol_move_changes(project, mover, target), apply, before, moved_code=True)


def move_module(project: Project, *, module: str, dest: str, apply: bool) -> None:
    before = source_bytes(project)
    mover = cast(MoveModule, create_move(project, resource(project, module)))
    _emit(project, module_move_changes(project, mover, _destination(project, dest, folder=True)), apply, before)


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
    if command in ("rename", "retarget", "rename-map"):
        entries, shown = _entries(command, project_root, options)
        rename_options = entry_options(options)
        return run_map(
            project, entries, rename_options, apply_=apply, map_shown=shown,
            module_rename=lambda r: _module_rename(project, _renamer(r.renamer), r.entry, rename_options, apply),
        )
    if command == "move-symbol":
        move_symbol(project, file=str(options["file"]), locator=_locator(options), dest=str(options["dest"]), apply=apply)
    else:
        move_module(project, module=str(options["module"]), dest=str(options["dest"]), apply=apply)
    return 0


def run_refactor(*, project_root: str, command: str, apply: bool, options: dict[str, Any]) -> int:
    """`dr-refactor` handler: 0 on success, 1 with the reason on stderr when the refactor cannot proceed or refuses,
    2 for a locator or map error, or a `--keep`, `--with` or `--without` site that matches nothing it must."""
    # rope documents `ropefolder=None` (no rope folder); its signature infers `str` from the default.
    project = Project(str(Path(project_root).resolve()), ropefolder=None)  # pyright: ignore[reportArgumentType]
    try:
        return _run(project, project_root, command, apply, options)
    except SiteError as exc:
        print(message(exc.template, site=exc.site), file=sys.stderr)
        return 2
    except (LocatorError, MapError) as exc:
        print(exc, file=sys.stderr)
        return 2
    except Refused as exc:
        print("\n".join(exc.lines), file=sys.stderr)
        return 1
    except MapConflict as exc:
        print(exc.text, file=sys.stderr)
        return 1
    except RefactorError as exc:
        print(exc, file=sys.stderr)
        return 1
    except WalkerGap as gap:
        print(message("refactor.rope-walk", path=gap.path, line=gap.line), file=sys.stderr)
        return 1
    except FileChanged as changed:
        print(message("refactor.file-changed", path=changed.path), file=sys.stderr)
        return 1
    except BaselineFailed:
        print(message("refactor.baseline-failed", language="python"), file=sys.stderr)
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
