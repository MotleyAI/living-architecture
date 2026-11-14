"""`dr-refactor`: IDE-grade Python refactors via rope (rename, move-symbol, move-module)."""

from __future__ import annotations

import difflib
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel
from rope.base import libutils
from rope.base.change import ChangeContents, ChangeSet
from rope.base.exceptions import BadIdentifierError, RefactoringError
from rope.base.project import Project
from rope.base.resources import File, Resource
from rope.refactor.move import MoveGlobal, MoveModule, create_move
from rope.refactor.rename import Rename

from living_architecture.config import ConfigError
from living_architecture.contract import message
from living_architecture.lang import LanguageServerError
from living_architecture.refactor.keyed import UnresolvedBase
from living_architecture.refactor.move_edits import NameConflict, module_move_changes, symbol_move_changes
from living_architecture.refactor.python_source import split_lines
from living_architecture.refactor.rename_union import FileChanged, RenameOptions, SymbolRename
from living_architecture.refactor.rope_patches import WalkerGap, apply_rope_patches
from living_architecture.refactor.sites import Keeps, SiteError

apply_rope_patches()


class RefactorError(Exception):
    """The refactor cannot be computed; the message is user-facing."""


class Locator(BaseModel):
    """Where the symbol is: an offset, a 1-based line/column, or the first def/class/use of a name."""

    offset: int | None = None
    line: int | None = None
    col: int | None = None
    name: str | None = None


def _offset_from_line_col(text: str, line: int, col: int) -> int:
    lines = split_lines(text)
    if not 1 <= line <= len(lines):
        raise RefactorError(message("refactor.line-out-of-range", line=line, count=len(lines)))
    return sum(len(lines[i]) for i in range(line - 1)) + (col - 1)


def _find_symbol_offset(text: str, name: str) -> int:
    escaped = re.escape(name)
    m = re.search(rf"^\s*(?:async\s+def|def|class)\s+({escaped})\b", text, re.MULTILINE)
    if m:
        return m.start(1)
    m = re.search(rf"\b{escaped}\b", text)
    if not m:
        raise RefactorError(message("refactor.symbol-not-found", name=name))
    return m.start()


def _resolve_offset(locator: Locator, text: str) -> int:
    if locator.offset is not None:
        return locator.offset
    if locator.line is not None:
        return _offset_from_line_col(text, locator.line, locator.col or 1)
    if locator.name is not None:
        return _find_symbol_offset(text, locator.name)
    raise RefactorError(message("refactor.no-locator"))


def _resource(project: Project, path: str) -> Resource:
    resolved = Path(path).resolve()
    resource = None
    if resolved.is_relative_to(Path(project.address).resolve()):
        resource = libutils.path_to_resource(project, str(resolved))
    if resource is None:
        raise RefactorError(message("refactor.outside-project", path=path))
    return resource


def _destination(project: Project, dest: str, *, folder: bool) -> Resource:
    """`--dest` as an existing directory (`folder`) or file in the project."""
    resolved = Path(dest).resolve()
    if resolved.is_relative_to(Path(project.address).resolve()) and not (
        resolved.is_dir() if folder else resolved.is_file()
    ):
        raise RefactorError(message("refactor.destination-missing", path=dest))
    return _resource(project, dest)


def _emit(project: Project, changes: ChangeSet, apply: bool, write: Callable[[], None] | None = None) -> None:
    """Print the changes sorted by path (rope's own order follows the hash seed); apply them with `write`, else
    through rope in its order."""
    ordered = sorted(changes.changes, key=lambda c: c.resource.path)
    print(f"{changes}:\n\n\n" + "".join(c.get_description() + "\n" for c in ordered))
    touched = [c.resource.path for c in ordered]
    if apply:
        if write is None:
            project.do(changes)
        else:
            write()
        print(message("refactor.applied", count=len(touched)))
        for p in touched:
            print(message("refactor.applied-file", path=p))
    else:
        print(message("refactor.dry-run", count=len(touched)))


def _refusal(symbol: SymbolRename) -> list[str]:
    """The lines refusing a member rename, or none when it may proceed."""
    blind = [] if symbol.options.allow_blindspots else [f.text for f in symbol.blindspots]
    if not blind and not symbol.stand_ins:
        return []
    closing = [message("refactor.blindspots", count=len(blind), attr=symbol.old)] if blind else []
    shown = blind or [f.text for f in symbol.blindspots]
    return [*shown, *(f.text for f in symbol.stand_ins), *closing]


def rename(project: Project, *, file: str, locator: Locator, new_name: str, options: RenameOptions, apply: bool) -> int:
    """0 when renamed (or dry-run), 1 when a member rename refuses; the refusal on stderr."""
    changes, symbol = _compute_rename(project, file, locator, new_name, options)
    if symbol is not None and (refusal := _refusal(symbol)):
        print("\n".join(refusal), file=sys.stderr)
        return 1
    if options.unsure:
        print(message("refactor.unsure-warning"))
    if changes is not None:
        _emit(project, changes, apply)
        return 0
    assert symbol is not None
    for finding in [*symbol.blindspots, *symbol.leftovers]:
        print(finding.text, file=sys.stderr)
    changes, texts = symbol.changes()
    if apply:
        symbol.verify(texts)
    _emit(project, changes, apply, lambda: symbol.write(texts))
    return 0


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


def _compute_rename(
    project: Project, file: str, locator: Locator, new_name: str, options: RenameOptions
) -> tuple[ChangeSet | None, SymbolRename | None]:
    """A module rename's rope changes, or a symbol rename computed; RefactorError when rope or the server refuses."""
    offset = _resolve_offset(locator, Path(file).read_text())
    changes = None
    symbol = None
    try:
        renamer = Rename(project, _resource(project, file), offset)
        if renamer._is_renaming_a_module():
            changes = _kept(project, renamer.get_changes(
                new_name, in_hierarchy=options.in_hierarchy, unsure=(lambda *_: True) if options.unsure else None
            ), options.keep)
        else:
            symbol = SymbolRename(project, renamer, new_name, options)
            symbol.compute()
    except (RefactoringError, BadIdentifierError):
        raise RefactorError(message("refactor.cannot-rename")) from None
    except LanguageServerError:
        raise RefactorError(message("refactor.pyright-failed")) from None
    except ConfigError as exc:
        raise RefactorError(str(exc)) from None
    except UnresolvedBase as base:
        root = Path(project.address).resolve()
        path = (base.path.relative_to(root) if base.path.is_relative_to(root) else base.path).as_posix()
        raise RefactorError(message("refactor.unresolved-base", name=base.name, path=path, line=base.line)) from None
    return changes, symbol


def move_symbol(project: Project, *, file: str, locator: Locator, dest: str, apply: bool) -> None:
    offset = _resolve_offset(locator, Path(file).read_text())
    mover = cast(MoveGlobal, create_move(project, _resource(project, file), offset))
    target = cast(File, _destination(project, dest, folder=False))
    if target == mover.source:
        _emit(project, ChangeSet(f"Moving global <{mover.old_name}>"), apply)
        return
    _emit(project, symbol_move_changes(project, mover, target), apply)


def move_module(project: Project, *, module: str, dest: str, apply: bool) -> None:
    mover = cast(MoveModule, create_move(project, _resource(project, module)))
    _emit(project, module_move_changes(project, mover, _destination(project, dest, folder=True)), apply)


def run_refactor(*, project_root: str, command: str, apply: bool, options: dict[str, Any]) -> int:
    """`dr-refactor` handler: 0 on success, 1 with the reason on stderr when the refactor cannot proceed or a member
    rename refuses, 2 for a `--keep`, `--with` or `--without` site that matches nothing it must."""
    # rope documents `ropefolder=None` (no rope folder); its signature infers `str` from the default.
    project = Project(str(Path(project_root).resolve()), ropefolder=None)  # pyright: ignore[reportArgumentType]
    try:
        locator = Locator(
            offset=options.get("offset"), line=options.get("line"), col=options.get("col"), name=options.get("name")
        )
        if command == "rename":
            return rename(
                project,
                file=str(options["file"]),
                locator=locator,
                new_name=str(options["new_name"]),
                options=RenameOptions(
                    in_hierarchy=bool(options["in_hierarchy"]),
                    unsure=options["unsure"] == "include",
                    allow_blindspots=bool(options.get("allow_blindspots")),
                    with_sites=tuple(options.get("with_stand_ins") or ()),
                    without_sites=tuple(options.get("without_stand_ins") or ()),
                    keep=tuple(options.get("keep") or ()),
                    docs=bool(options.get("docs")),
                ),
                apply=apply,
            )
        if command == "move-symbol":
            move_symbol(project, file=str(options["file"]), locator=locator, dest=str(options["dest"]), apply=apply)
        else:
            move_module(project, module=str(options["module"]), dest=str(options["dest"]), apply=apply)
    except SiteError as exc:
        print(message(exc.template, site=exc.site), file=sys.stderr)
        return 2
    except RefactorError as exc:
        print(exc, file=sys.stderr)
        return 1
    except WalkerGap as gap:
        print(message("refactor.rope-walk", path=gap.path, line=gap.line), file=sys.stderr)
        return 1
    except FileChanged as changed:
        print(message("refactor.file-changed", path=changed.path), file=sys.stderr)
        return 1
    except NameConflict as conflict:
        print(message("refactor.name-conflict", name=conflict.name, path=conflict.path, line=conflict.line), file=sys.stderr)
        return 1
    finally:
        project.close()
    return 0
