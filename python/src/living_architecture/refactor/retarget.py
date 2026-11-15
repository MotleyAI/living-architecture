"""`retarget`: the rename of an alias to its target's name without the alias's own declarations, refused where a
subclass overrides the alias or the target's name means something else, dropping imports it would duplicate."""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterator

from rope.base import libutils
from rope.refactor.rename import Rename
from typing_extensions import override

from living_architecture.contract import message
from living_architecture.refactor.outcomes import Finding
from living_architecture.refactor.python_source import SourceFile, split_lines
from living_architecture.refactor.rename_union import RenameOptions, Session, SymbolRename
from living_architecture.refactor.rope_patches import every_parameter
from living_architecture.refactor.text_edits import TextEdit

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def module_name(session: Session, rel: str) -> str:
    return libutils.modname(session.project.get_resource(rel))


def _imported_module(stmt: ast.ImportFrom, importer: str, is_package: bool) -> str:
    if stmt.level == 0:
        return stmt.module or ""
    parts = importer.split(".") if is_package else importer.split(".")[:-1]
    parts = parts[: len(parts) - (stmt.level - 1)]
    return ".".join([*parts, *([stmt.module] if stmt.module else [])])


def _stored(node: ast.AST) -> Iterator[str]:
    """The names `node` binds, without entering a nested scope's body."""
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        yield node.id
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        yield node.name
        return
    elif isinstance(node, ast.alias):
        yield node.asname or node.name.split(".")[0]
    elif isinstance(node, ast.ExceptHandler) and node.name or isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
        yield node.name
    if isinstance(node, (ast.Lambda, *_COMPREHENSIONS)):
        return
    for child in ast.iter_child_nodes(node):
        yield from _stored(child)


def _binds(scope: ast.AST, name: str, accepted: Callable[[ast.AST], bool]) -> bool:
    """`scope` (a function, lambda, comprehension or class) binds `name` in its own body, `accepted` statements
    aside."""
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        if any(a.arg == name for a in every_parameter(scope.args)):
            return True
        body = scope.body if isinstance(scope.body, list) else [scope.body]
        return any(name in _stored(stmt) for stmt in body if not accepted(stmt))
    if isinstance(scope, _COMPREHENSIONS):
        return any(name in _stored(g.target) for g in scope.generators)
    if isinstance(scope, ast.ClassDef):
        return any(name in _stored(stmt) for stmt in scope.body if not accepted(stmt))
    return False


def _bound_in_scope(parents: dict[ast.AST, ast.AST], node: ast.AST, name: str, accepted: Callable[[ast.AST], bool]) -> bool:
    """A function, comprehension or the innermost class enclosing `node` binds `name`, `accepted` statements aside."""
    scope = parents.get(node)
    innermost = True
    while scope is not None:
        if isinstance(scope, (*_FUNCTIONS, *_COMPREHENSIONS)) or (innermost and isinstance(scope, ast.ClassDef)):
            if _binds(scope, name, accepted):
                return True
            innermost = innermost and not isinstance(scope, _FUNCTIONS)
        scope = parents.get(scope)
    return False


class AliasRetarget(SymbolRename):
    """References to an alias rewritten to name its target; the alias stays."""

    def __init__(self, session: Session, renamer: Rename, target: str, options: RenameOptions, *, line: int) -> None:
        super().__init__(session, renamer, target, options)
        self.check_names = False
        self.line = line
        self.refusals: list[Finding] = []
        self._parents: dict[str, dict[ast.AST, ast.AST]] = {}

    @override
    def header(self) -> str:
        return message("refactor.retarget-header", old=self.old, new=self.new)

    def retarget(self) -> None:
        """Drop the edits at the alias's own declarations and at a module's re-export of it, then refuse overrides and
        shadowed names and drop duplicate imports."""
        own = set(self.seeds)
        kept: dict[str, list[tuple[int, int]]] = {}
        for path in {e.path for e in self.edits}:
            kept[path] = _reexport_spans(self.snapshot.source(path), self.old)
        self.edits = [e for e in self.edits if (e.path, e.start) not in own
                      and not any(start <= e.start < end for start, end in kept[e.path])]
        self._overrides()
        alias_module = module_name(self.session, self.renamer.resource.path)
        edits: list[TextEdit] = []
        for edit in self.edits:
            edits.append(self._import_or_reference(edit, alias_module))
        self.edits = edits

    def _overrides(self) -> None:
        if not self.member:
            return
        hierarchy = self._hierarchy(self.renamer)
        rel = self.renamer.resource.path
        own = next((d.cls for d in self._declarations if d.rel == rel and d.line == self.line), None)
        for d in self._declarations:
            if (d.rel, d.start) in hierarchy and not (d.rel == rel and d.cls == own):
                text = message("refactor.retarget-override", path=d.rel, line=d.line, cls=d.cls, name=self.old)
                self.refusals.append(Finding(path=d.rel, line=d.line, col=d.start, text=text))

    def _import_or_reference(self, edit: TextEdit, alias_module: str) -> TextEdit:
        source = self.snapshot.source(edit.path)
        if source.tree is None:
            return edit
        if edit.path not in self._parents:
            self._parents[edit.path] = {child: node for node in ast.walk(source.tree) for child in ast.iter_child_nodes(node)}
        parents = self._parents[edit.path]
        node = _named_at(source, edit.start, self.old)
        if isinstance(node, ast.alias) and isinstance(stmt := parents.get(node), ast.ImportFrom):
            removal = self._duplicate(source, edit.path, stmt, node, parents, alias_module)
            if removal is not None:
                return removal
            if self._module_binds_other(source, edit.path, alias_module, skip=stmt):
                self._shadowed(source, edit)
        elif isinstance(node, ast.Name) and (
            _bound_in_scope(parents, node, self.new, lambda stmt: self._imports_target(edit.path, stmt, alias_module))
            or (edit.path != self.renamer.resource.path and self._module_binds_other(source, edit.path, alias_module))
        ):
            self._shadowed(source, edit)
        return edit

    def _shadowed(self, source: SourceFile, edit: TextEdit) -> None:
        line = source.line(edit.start)
        text = message("refactor.retarget-shadowed", path=edit.path, line=line, name=self.new)
        self.refusals.append(Finding(path=edit.path, line=line, col=edit.start, text=text))

    def _from_alias_module(self, rel: str, stmt: ast.ImportFrom, alias_module: str) -> bool:
        return _imported_module(stmt, module_name(self.session, rel), rel.endswith("__init__.py")) == alias_module

    def _imports_target(self, rel: str, stmt: ast.AST, alias_module: str) -> bool:
        """`stmt` imports the target's name from the alias's module."""
        return (isinstance(stmt, ast.ImportFrom) and self._from_alias_module(rel, stmt, alias_module)
                and any(a.name == self.new and a.asname in (None, self.new) for a in stmt.names))

    def _module_binds_other(self, source: SourceFile, rel: str, alias_module: str, skip: ast.AST | None = None) -> bool:
        """The module binds the target's name other than by importing it from the alias's module."""
        assert source.tree is not None
        return any(
            stmt is not skip and self.new in _stored(stmt) and not self._imports_target(rel, stmt, alias_module)
            for stmt in source.tree.body
        )

    def _duplicate(
        self, source: SourceFile, rel: str, stmt: ast.ImportFrom, alias: ast.alias, parents: dict[ast.AST, ast.AST],
        alias_module: str,
    ) -> TextEdit | None:
        """The removal of `alias` from its import when its scope already imports the target from the alias's
        module."""
        if alias.asname is not None:
            return None
        body = getattr(parents.get(stmt), "body", [])
        others = [s for s in body if isinstance(s, ast.ImportFrom) and self._from_alias_module(rel, s, alias_module)]
        if not any(a.name == self.new and a.asname in (None, self.new) for s in others for a in s.names):
            return None
        if len(stmt.names) == 1:
            return _statement_removal(source, rel, stmt)
        spans = [source.span(a) for a in stmt.names]  # pyright: ignore[reportArgumentType]
        i = next(k for k, a in enumerate(stmt.names) if a is alias)
        start, end = (spans[i][0], spans[i + 1][0]) if i + 1 < len(spans) else (spans[i - 1][1], spans[i][1])
        return TextEdit(path=rel, start=start, end=end, new_text="")


def _reexport_spans(source: SourceFile, name: str) -> list[tuple[int, int]]:
    """Where a module re-exports `name` (its `__all__` lists it): the `__all__` strings and its imports of `name`."""
    if source.tree is None:
        return []
    names = [n for stmt in source.tree.body if _assigns_all(stmt) for n in ast.walk(stmt)
             if isinstance(n, ast.Constant) and n.value == name]
    if not names:
        return []
    imports = [a for stmt in source.tree.body if isinstance(stmt, (ast.Import, ast.ImportFrom)) for a in stmt.names
               if (a.asname or a.name.split(".")[-1]) == name]
    return [source.span(n) for n in [*names, *imports]]  # pyright: ignore[reportArgumentType]


def _assigns_all(stmt: ast.stmt) -> bool:
    """`stmt` assigns or extends a module's `__all__`."""
    if isinstance(stmt, ast.Assign):
        targets = stmt.targets
    elif isinstance(stmt, (ast.AnnAssign, ast.AugAssign)):
        targets = [stmt.target]
    else:
        return False
    return any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets)


def _statement_removal(source: SourceFile, rel: str, stmt: ast.stmt) -> TextEdit:
    """The removal of `stmt`: its whole lines when nothing but a comment shares them, else the statement and its
    `;` separator."""
    start, end = source.span(stmt)
    first = source.line_start(stmt.lineno)
    end_line = stmt.end_lineno or stmt.lineno
    after_last = source.line_start(end_line + 1) if end_line < len(split_lines(source.text)) else len(source.text)
    before, after = source.text[first:start], source.text[end:after_last].lstrip(" \t")
    if not before.strip() and (not after.strip() or after.startswith("#")):
        return TextEdit(path=rel, start=first, end=after_last, new_text="")
    if after.startswith(";"):
        return TextEdit(path=rel, start=start, end=after_last - len(after[1:].lstrip(" \t")), new_text="")
    return TextEdit(path=rel, start=first + len(before.rstrip(" \t")) - 1, end=end, new_text="")


def _named_at(source: SourceFile, offset: int, name: str) -> ast.AST | None:
    """The `ast.Name` or imported `ast.alias` naming `name` at `offset`."""
    assert source.tree is not None
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Name) and node.id == name and source.span(node)[0] == offset:
            return node
        if isinstance(node, ast.alias) and node.name == name and source.offset(node.lineno, node.col_offset) == offset:
            return node
    return None
