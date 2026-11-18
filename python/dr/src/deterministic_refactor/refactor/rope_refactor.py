"""`dr-refactor`: Python refactors, all computed by la: renames, rename maps, retargets and moves (`move-symbol`,
`move-module`); rope only checks a move's files for walker gaps."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from deterministic_refactor.contract import message
from deterministic_refactor.refactor.baseline_align import BaselineFailed
from deterministic_refactor.refactor.diff_render import edit_description, move_description
from deterministic_refactor.refactor.generate_map import generate_map
from deterministic_refactor.refactor.locators import (
    Locator,
    RefactorError,
    named_source,
    offset_from_line_col,
    resolve,
)
from deterministic_refactor.refactor.map_file import MapEntry, MapError, load_map
from deterministic_refactor.refactor.module_move import module_move_texts
from deterministic_refactor.refactor.move_edits import NameConflict
from deterministic_refactor.refactor.move_project import MoveProject
from deterministic_refactor.refactor.move_verify import verify
from deterministic_refactor.refactor.moved_imports import GuardedImport
from deterministic_refactor.refactor.moved_symbol import MovedSymbol, locate_moved
from deterministic_refactor.refactor.output_check import checked_write
from deterministic_refactor.refactor.progress import Progress, Refusal, Refused, refusal
from deterministic_refactor.refactor.rename_map import (
    baseline_failed,
    baseline_probe,
    emit,
    entry_options,
    run_map,
    walker_gaps,
)
from deterministic_refactor.refactor.rope_patches import WalkerGap, apply_rope_patches
from deterministic_refactor.refactor.routing import language_files
from deterministic_refactor.refactor.symbol_move import symbol_move_texts
from deterministic_refactor.refactor.symbol_path import LocatorError, is_wildcard, wildcard_refused
from deterministic_refactor.refactor.timings import timed
from deterministic_refactor.refactor.writer import FileChanged, FileMove, FileWrite, WriteFailed

apply_rope_patches()

__all__ = ["Locator", "RefactorError", "run_refactor"]

_offset_from_line_col = offset_from_line_col


def _emit(project: MoveProject, header: str, texts: dict[str, str], moves: list[FileMove], apply: bool,
          progress: Progress, *, symbol: tuple[MovedSymbol, str, str] | None = None) -> None:
    """Print the move's changes sorted by path, each file's diff at the path it was read at; write them all or nothing
    with `apply`, refusing a file that changed since it was read. `symbol` is a `move-symbol`'s declaration with its
    source and destination files. Refuses first when a file's new text is not valid or a name would resolve
    differently."""
    snapshot = project.snapshot
    writes = [checked_write(snapshot, rel, text) for rel, text in texts.items()]
    if writes or moves:
        with timed("references"):
            verify(project, symbol, writes, moves)
    described = [(rel, edit_description(rel, snapshot.text(rel), text)) for rel, text in texts.items()]
    described += [(m.rel, move_description(m.rel, m.dest)) for m in moves]
    unchanged = [FileWrite(rel=rel, old=snapshot.data(rel), new=snapshot.data(rel)) for rel in snapshot.read()
                 if rel not in texts and any(rel == m.rel or rel.startswith(m.rel + "/") for m in moves)]
    emit(project.root, [header], described, apply, writes, moves, progress, moved_code=symbol is not None,
         unchanged=unchanged)


def _checks(project: MoveProject, progress: Progress, failures: list[Refusal], names: set[str], source: Path) -> None:
    """The `checks` phase of a move: walker gaps in the files spelling `names`, the checker; `Refused` with them
    and the resolution `failures`."""
    progress.phase("checks")
    failures = [*failures, *walker_gaps(project.root, project.snapshot.text, names), *baseline_probe(project.root, source)]
    if failures:
        raise Refused(failures)
    progress.phase("references")


def _first_source(path: Path) -> Path:
    """`path`, or the first Python file under the directory."""
    if not path.is_dir():
        return path
    return next(iter(language_files(path, "python")), path)


def move_symbol(root: Path, *, file: str, locator: Locator, dest: str, apply: bool, progress: Progress) -> None:
    project = MoveProject(root)
    progress.phase("resolve")
    failures: list[Refusal] = []
    moved: MovedSymbol | None = None
    source = target = ""
    try:
        with timed("resolve"):
            source = project.rel(file)
            text = named_source(project.snapshot, source)
            if is_wildcard(locator.symbol):
                raise wildcard_refused(file, str(locator.symbol))
            offset, located = resolve(locator, text, file)
            module = project.module(source)
            if (located is not None and not located.top_level) or module is None:
                raise RefactorError(message("refactor.not-movable", path=file))
            project.unique(source)
            moved = locate_moved(text, module, offset, file)
            target = project.destination(dest, folder=False)
            if target != source and named_source(project.snapshot, target).tree is None:
                raise RefactorError(message("refactor.unparsable", path=target))
    except LocatorError as exc:
        failures.append(refusal(str(exc), 2))
    except RefactorError as exc:
        failures.append(refusal(str(exc)))
    _checks(project, progress, failures, {moved.name} if moved is not None else set(), Path(file))
    assert moved is not None
    header = message("refactor.move-symbol-header", name=moved.name)
    if target == source:
        _emit(project, header, {}, [], apply, progress)
        return
    with timed("references"):
        texts = symbol_move_texts(project, source, moved, target)
    _emit(project, header, texts, [], apply, progress, symbol=(moved, source, target))


def move_module(root: Path, *, module: str, dest: str, apply: bool, progress: Progress) -> None:
    project = MoveProject(root)
    progress.phase("resolve")
    failures: list[Refusal] = []
    source = folder = ""
    try:
        with timed("resolve"):
            source = project.rel(module)
            folder = project.destination(dest, folder=True)
            project.unique(source)
            moved = Path(source).parent if Path(source).name == "__init__.py" else Path(source)
            if Path(folder).is_relative_to(moved):
                raise RefactorError(message("refactor.destination-inside-source", path=folder, source=moved.as_posix()))
            taken = (Path(folder) / moved.name).as_posix()
            if os.path.lexists(root / taken):
                raise RefactorError(message("refactor.destination-exists", path=taken))
    except RefactorError as exc:
        failures.append(refusal(str(exc)))
    named = Path(module).parent if Path(module).name == "__init__.py" else Path(module)
    name = named.name if named.is_dir() else named.stem
    _checks(project, progress, failures, {name}, _first_source(Path(module)))
    with timed("references"):
        move, texts = module_move_texts(project, source, folder)
    _emit(project, message("refactor.move-module-header", name=move.basename), texts, [move.move], apply, progress)


def _locator(options: dict[str, Any]) -> Locator:
    return Locator(offset=options.get("offset"), line=options.get("line"), col=options.get("col"),
                   symbol=options.get("symbol"))


def _entries(command: str, project_root: str, options: dict[str, Any]) -> tuple[list[MapEntry], str]:
    """The map a `rename`, `retarget` or `rename-map` runs, and the map as named in findings: a `rename` without a
    locator is the one module entry of its file."""
    if command == "rename-map":
        return load_map(str(options["map"]), project_root), str(options["map"])
    file = str(options["file"])
    locator = _locator(options)
    if command == "rename" and not locator.model_dump(exclude_none=True):
        return [MapEntry(index=1, file=file, path=file, new_name=str(options["new_name"]), module=True)], ""
    if command == "rename":
        return [MapEntry(index=1, file=file, path=file, locator=locator, new_name=str(options["new_name"]))], ""
    return [MapEntry(index=1, file=file, path=file, locator=locator, retarget=str(options["target"]))], ""


def _run(project_root: str, command: str, apply: bool, options: dict[str, Any]) -> int:
    if command == "generate-map":
        return generate_map(Path(project_root).resolve(), str(options["table"]))
    progress = Progress()
    root = Path(project_root).resolve()
    if command in ("rename", "retarget", "rename-map"):
        entries, shown = _entries(command, project_root, options)
        return run_map(root, entries, entry_options(options), apply_=apply, map_shown=shown, progress=progress)
    if command == "move-symbol":
        move_symbol(root, file=str(options["file"]), locator=_locator(options), dest=str(options["dest"]), apply=apply,
                    progress=progress)
    else:
        move_module(root, module=str(options["module"]), dest=str(options["dest"]), apply=apply, progress=progress)
    return 0


def run_refactor(*, project_root: str, command: str, apply: bool, options: dict[str, Any]) -> int:
    """`dr-refactor` handler: 0 on success, else the highest exit code of the refusals on stderr: 1 when the refactor
    cannot proceed or refuses, 2 for a locator or map error, or a `--keep`, `--with` or `--without` site that matches
    nothing it must."""
    try:
        return _run(project_root, command, apply, options)
    except (LocatorError, MapError) as exc:
        print(exc, file=sys.stderr)
        return 2
    except Refused as exc:
        if exc.lines:
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
    except GuardedImport as guarded:
        print(message("refactor.guarded-import", path=guarded.path, line=guarded.line), file=sys.stderr)
        return 1
