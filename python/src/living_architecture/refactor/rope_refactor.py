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
)
from living_architecture.refactor.rename_union import RenameOptions
from living_architecture.refactor.rope_patches import WalkerGap, apply_rope_patches
from living_architecture.refactor.sites import Keeps, SiteError
from living_architecture.refactor.symbol_path import LocatorError
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


def _emit(project: Project, changes: ChangeSet, apply: bool) -> None:
    """Print a rope change set sorted by path; write it all or nothing with `apply`."""
    writes, moves = change_set_writes(project, changes)
    emit(project, [f"{changes}:"], changes, apply, writes, moves)


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


def _module_rename(project: Project, renamer: Rename, entry: MapEntry, options: RenameOptions, apply: bool) -> int:
    """rope's rename of a module, its `--keep` sites left."""
    if entry.new_name is None:
        raise RefactorError(message("refactor.cannot-rename"))
    if options.with_sites or options.without_sites:
        raise SiteError("refactor.not-stand-in", (*options.with_sites, *options.without_sites)[0])
    try:
        changes = renamer.get_changes(
            entry.new_name, in_hierarchy=options.in_hierarchy, unsure=(lambda *_: True) if options.unsure else None
        )
    except (RefactoringError, BadIdentifierError):
        raise RefactorError(message("refactor.cannot-rename")) from None
    _emit(project, _kept(project, changes, options.keep), apply)
    return 0


def move_symbol(project: Project, *, file: str, locator: Locator, dest: str, apply: bool) -> None:
    offset, located = resolve(locator, file)
    if located is not None and not located.top_level:
        raise RefactorError(message("refactor.not-movable", path=file))
    mover = cast(MoveGlobal, create_move(project, resource(project, file), offset))
    target = cast(File, _destination(project, dest, folder=False))
    if target == mover.source:
        _emit(project, ChangeSet(f"Moving global <{mover.old_name}>"), apply)
        return
    _emit(project, symbol_move_changes(project, mover, target), apply)


def move_module(project: Project, *, module: str, dest: str, apply: bool) -> None:
    mover = cast(MoveModule, create_move(project, resource(project, module)))
    _emit(project, module_move_changes(project, mover, _destination(project, dest, folder=True)), apply)


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
            module_rename=lambda r: _module_rename(project, r.renamer, r.entry, rename_options, apply),
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
    except WriteFailed as failed:
        print(message("refactor.write-failed", path=failed.path), file=sys.stderr)
        return 1
    except NameConflict as conflict:
        print(message("refactor.name-conflict", name=conflict.name, path=conflict.path, line=conflict.line), file=sys.stderr)
        return 1
    finally:
        project.close()
