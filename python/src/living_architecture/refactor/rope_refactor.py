"""`dr-refactor`: Python refactors: renames, rename maps and retargets computed by la, moves (`move-symbol`,
`move-module`) by rope."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, cast

from rope.base import libutils
from rope.base.change import ChangeSet
from rope.base.project import Project
from rope.base.resources import File, Resource
from rope.refactor.move import MoveGlobal, MoveModule, create_move

from living_architecture.contract import message
from living_architecture.refactor.baseline_align import BaselineFailed
from living_architecture.refactor.entry_location import Entry
from living_architecture.refactor.locators import Locator, RefactorError, offset_from_line_col, resolve
from living_architecture.refactor.map_file import MapEntry, MapError, load_map
from living_architecture.refactor.module_rename import run_module_rename
from living_architecture.refactor.move_edits import NameConflict, module_move_changes, symbol_move_changes
from living_architecture.refactor.progress import Progress, Refusal, Refused, refusal
from living_architecture.refactor.python_project import Snapshot
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
from living_architecture.refactor.rope_patches import WalkerGap, apply_rope_patches
from living_architecture.refactor.routing import language_files
from living_architecture.refactor.symbol_path import LocatorError
from living_architecture.refactor.timings import timed
from living_architecture.refactor.writer import FileChanged, WriteFailed

apply_rope_patches()

__all__ = ["Locator", "RefactorError", "run_refactor"]

_offset_from_line_col = offset_from_line_col


def resource(project: Project, path: str) -> Resource:
    resolved = Path(path).resolve()
    found = None
    if resolved.is_relative_to(Path(project.address).resolve()):
        found = libutils.path_to_resource(project, str(resolved))
    if found is None:
        raise RefactorError(message("refactor.outside-project", path=path))
    return found


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
    described = [(c.resource.path, c.get_description()) for c in changes.changes]
    emit(Path(project.address), [f"{changes}:"], described, apply, writes, moves, progress, moved_code=moved_code)


def _checks(project: Project, progress: Progress, failures: list[Refusal], names: set[str], source: Path) -> None:
    """The `checks` phase of a move: walker gaps in the files spelling `names`, the checker; `Refused` with them
    and the resolution `failures`."""
    progress.phase("checks")
    root = Path(project.address).resolve()
    failures = [*failures, *walker_gaps(root, Snapshot(root).text, names), *baseline_probe(root, source)]
    if failures:
        raise Refused(failures)
    progress.phase("references")


def _rope_offset(snapshot: Snapshot, rel: str, offset: int) -> int:
    """An offset in `rel`'s text as read as an offset in rope's text: line endings as `\\n`, a byte order mark kept."""
    return offset - snapshot.text(rel).count("\r\n", 0, offset) + snapshot.has_bom(rel)


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
            moved = resource(project, file)
            snapshot = Snapshot(Path(project.address).resolve())
            offset, located = resolve(locator, snapshot.source(moved.path), file)
            if located is not None and not located.top_level:
                raise RefactorError(message("refactor.not-movable", path=file))
            mover = cast(MoveGlobal, create_move(project, moved, _rope_offset(snapshot, moved.path, offset)))
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


def _located(entry: Entry | None) -> Entry:
    assert entry is not None
    return entry


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


class _RopeProject:
    """rope's project of a move, built at first need."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._project: Project | None = None

    def get(self) -> Project:
        if self._project is None:
            with timed("load"):
                # rope documents `ropefolder=None` (no rope folder); its signature infers `str` from the default.
                self._project = Project(str(self.root), ropefolder=None)  # pyright: ignore[reportArgumentType]
        return self._project

    def close(self) -> None:
        if self._project is not None:
            self._project.close()


def _run(rope: _RopeProject, project_root: str, command: str, apply: bool, options: dict[str, Any]) -> int:
    progress = Progress()
    if command in ("rename", "retarget", "rename-map"):
        entries, shown = _entries(command, project_root, options)
        rename_options = entry_options(options)
        return run_map(
            rope.root, entries, rename_options, apply_=apply, map_shown=shown, progress=progress,
            module_rename=lambda engine, r: run_module_rename(engine.session, engine.locator, _located(r.located),
                                                              r.entry.new_name, rename_options, apply, progress,
                                                              stub=engine.stub),
            file_modules=command == "rename",
        )
    if command == "move-symbol":
        move_symbol(rope.get(), file=str(options["file"]), locator=_locator(options), dest=str(options["dest"]),
                    apply=apply, progress=progress)
    else:
        move_module(rope.get(), module=str(options["module"]), dest=str(options["dest"]), apply=apply, progress=progress)
    return 0


def run_refactor(*, project_root: str, command: str, apply: bool, options: dict[str, Any]) -> int:
    """`dr-refactor` handler: 0 on success, else the highest exit code of the refusals on stderr: 1 when the refactor
    cannot proceed or refuses, 2 for a locator or map error, or a `--keep`, `--with` or `--without` site that matches
    nothing it must."""
    rope = _RopeProject(Path(project_root).resolve())
    try:
        return _run(rope, project_root, command, apply, options)
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
        rope.close()
