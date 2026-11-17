"""`move-module` for Python: each import of the module rewritten in place, each use that no longer resolves rewritten,
then the module's file or directory moved."""

from __future__ import annotations

import ast
from pathlib import Path

from living_architecture.refactor.move_edits import File, from_name, named
from living_architecture.refactor.move_project import MoveProject
from living_architecture.refactor.writer import FileMove

_INIT = "__init__.py"


class ModuleMove:
    """The paths of one `move-module` of `source` (a file or a directory) into folder `dest`, and the per-file rewrites
    of its imports and uses."""

    def __init__(self, project: MoveProject, source: str, dest: str) -> None:
        if Path(source).name == _INIT:
            source = Path(source).parent.as_posix()
        self.project = project
        self.source = source
        self.basename = Path(source).stem if source.endswith(".py") else Path(source).name
        self.old = project.dotted(source)
        dest_name = project.dotted(dest)
        self.new = f"{dest_name}.{self.basename}" if dest_name else self.basename
        self.new_parent = self.new.rpartition(".")[0]
        self.old_parent = self.old.rpartition(".")[0]
        self.move = FileMove(rel=source, dest=f"{dest}/{Path(source).name}" if dest else Path(source).name)

    def mapped(self, name: str) -> str | None:
        return self.new + name[len(self.old) :] if name == self.old or name.startswith(self.old + ".") else None

    def moves(self, rel: str) -> bool:
        return rel == self.source or rel.startswith(self.source + "/")

    def new_package(self, rel: str) -> str:
        name = self.project.dotted(rel)
        new_name = self.mapped(name) or name
        return new_name if Path(rel).name == _INIT else new_name.rpartition(".")[0]

    def rewrite_import(self, file: File, stmt: ast.Import) -> None:
        for index, alias in enumerate(stmt.names):
            target = self.mapped(alias.name)
            if target is None:
                continue
            file.rewrite_dotted(stmt, index, target)
            file.rewritten.add(id(stmt))
            if not alias.asname:
                file.plain_now[id(alias)] = target

    def rewrite_from(self, file: File, stmt: ast.ImportFrom, moved: bool, package: str) -> None:
        base = file.binder.from_module(stmt)
        if base is None:
            return
        current = "." * stmt.level + (stmt.module or "")
        relocated = moved and stmt.level > 0
        target = self.mapped(base)
        hits = self._hits(stmt, base)
        if target is not None:
            if not relocated and from_name(stmt, package, target) != current:
                file.rewrite_module(stmt, from_name(stmt, package, target))
                file.rewritten.add(id(stmt))
            return
        if hits and len(hits) == len(stmt.names):
            file.rewrite_module(stmt, from_name(stmt, package, self.new_parent) if self.new_parent else "")
            file.rewritten.add(id(stmt))
            return
        if hits:
            self._split(file, stmt, hits, package)
        if relocated and from_name(stmt, package, base) != current:
            file.rewrite_module(stmt, from_name(stmt, package, base))

    def _hits(self, stmt: ast.ImportFrom, base: str) -> list[int]:
        if base != self.old_parent:
            return []
        return [i for i, alias in enumerate(stmt.names) if alias.name == self.basename]

    def _split(self, file: File, stmt: ast.ImportFrom, hits: list[int], package: str) -> None:
        for hit in hits:
            file.remove_item(stmt, hit)
        aliases = named([stmt.names[i] for i in hits])
        line = f"from {from_name(stmt, package, self.new_parent)} import {aliases}" if self.new_parent else f"import {aliases}"
        file.after.append((stmt, line))

    def rewrite_uses(self, file: File) -> None:
        """Rule 3 for each use reaching the module only as an attribute of its parent package; rule 2 keeps a use the
        package binds explicitly (or answers through a module-level `__getattr__`)."""
        resolver = self.project.resolver
        for node, scope in file.attributes:
            if node.attr != self.basename or resolver.resolve(file.module, scope, node.value) != ("module", self.old_parent):
                continue
            if not self._binds(self.old_parent) and resolver.member(self.old_parent, self.basename) == ("module", self.old):
                file.rewrite_use(node, scope, self.new, self.new)

    def _binds(self, package: str) -> bool:
        loaded = self.project.resolver.load(package)
        return loaded is not None and any(name in loaded.scope.bindings for name in (self.basename, "__getattr__"))

    def edit(self, rel: str) -> str | None:
        """`rel`'s text after the move's edits; None when the file holds nothing to edit."""
        moved = self.moves(rel)
        if not moved and self.basename not in self.project.snapshot.text(rel):
            return None
        if self.project.module(rel) is None:
            return None
        file = File(self.project, rel, self.project.package(rel))
        package = self.new_package(rel) if moved else file.package
        for stmt, _, _ in file.binder.imports:
            if isinstance(stmt, ast.Import):
                self.rewrite_import(file, stmt)
            else:
                self.rewrite_from(file, stmt, moved, package)
        self.rewrite_uses(file)
        return file.finish()


def module_move_texts(project: MoveProject, source: str, dest: str) -> tuple[ModuleMove, dict[str, str]]:
    """The move, and each file's new text where it changes (moved files at their old paths)."""
    move = ModuleMove(project, source, dest)
    texts: dict[str, str] = {}
    for rel in project.files():
        text = move.edit(rel)
        if text is not None and text != project.snapshot.text(rel):
            texts[rel] = text
    return move, texts
