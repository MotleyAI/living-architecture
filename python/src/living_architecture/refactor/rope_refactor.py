"""`dr-refactor`: IDE-grade Python refactors via rope (rename, move-symbol, move-module)."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel
from rope.base import libutils
from rope.base.change import ChangeSet
from rope.base.project import Project
from rope.base.resources import Resource
from rope.refactor.move import MoveGlobal, MoveModule, create_move
from rope.refactor.rename import Rename

from living_architecture.contract import message
from living_architecture.refactor.rope_patches import apply_rope_patches

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
    lines = text.splitlines(keepends=True)
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


def _emit(project: Project, changes: ChangeSet, apply: bool) -> None:
    """Print the changes sorted by path (rope's own order follows the hash seed); apply in rope's order."""
    ordered = sorted(changes.changes, key=lambda c: c.resource.path)
    print(f"{changes}:\n\n\n" + "".join(c.get_description() + "\n" for c in ordered))
    touched = [c.resource.path for c in ordered]
    if apply:
        project.do(changes)
        print(message("refactor.applied", count=len(touched)))
        for p in touched:
            print(message("refactor.applied-file", path=p))
    else:
        print(message("refactor.dry-run", count=len(touched)))


def rename(
    project: Project, *, file: str, locator: Locator, new_name: str, in_hierarchy: bool, unsure: str, apply: bool
) -> None:
    offset = _resolve_offset(locator, Path(file).read_text())
    renamer = Rename(project, _resource(project, file), offset)
    if unsure == "include":
        print(message("refactor.unsure-warning"))
    changes = renamer.get_changes(
        new_name, in_hierarchy=in_hierarchy, unsure=(lambda *_: True) if unsure == "include" else None
    )
    _emit(project, changes, apply)


def move_symbol(project: Project, *, file: str, locator: Locator, dest: str, apply: bool) -> None:
    offset = _resolve_offset(locator, Path(file).read_text())
    mover = cast(MoveGlobal, create_move(project, _resource(project, file), offset))
    _emit(project, mover.get_changes(_resource(project, dest)), apply)


def move_module(project: Project, *, module: str, dest: str, apply: bool) -> None:
    mover = cast(MoveModule, create_move(project, _resource(project, module)))
    _emit(project, mover.get_changes(_resource(project, dest)), apply)


def run_refactor(*, project_root: str, command: str, apply: bool, options: dict[str, Any]) -> int:
    """`dr-refactor` handler: 0 on success, 1 with the reason on stderr when rope cannot proceed."""
    project = Project(str(Path(project_root).resolve()))
    try:
        locator = Locator(
            offset=options.get("offset"), line=options.get("line"), col=options.get("col"), name=options.get("name")
        )
        if command == "rename":
            rename(
                project,
                file=str(options["file"]),
                locator=locator,
                new_name=str(options["new_name"]),
                in_hierarchy=bool(options["in_hierarchy"]),
                unsure=str(options["unsure"]),
                apply=apply,
            )
        elif command == "move-symbol":
            move_symbol(project, file=str(options["file"]), locator=locator, dest=str(options["dest"]), apply=apply)
        else:
            move_module(project, module=str(options["module"]), dest=str(options["dest"]), apply=apply)
    except RefactorError as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        project.close()
    return 0
