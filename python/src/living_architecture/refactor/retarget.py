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


def _stored(node: ast.AST, skip: Callable[[ast.AST], bool] = lambda _: False) -> Iterator[str]:
    """The names `node` binds, without entering a nested scope's body or a node `skip` accepts."""
    if skip(node):
        return
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
        yield from _stored(child, skip)


def _binds(scope: ast.AST, name: str, accepted: Callable[[ast.AST], bool]) -> bool:
    """`scope` (a function, lambda, comprehension or class) binds `name` in its own body, `accepted` statements
    aside."""
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        if any(a.arg == name for a in every_parameter(scope.args)):
            return True
        body = scope.body if isinstance(scope.body, list) else [scope.body]
        return any(name in _stored(stmt, accepted) for stmt in body)
    if isinstance(scope, _COMPREHENSIONS):
        return any(name in _stored(g.target) for g in scope.generators)
    if isinstance(scope, ast.ClassDef):
        return any(name in _stored(stmt, accepted) for stmt in scope.body)
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
        self._shims: dict[str, bool] = {}

    @override
    def header(self) -> str:
        return message("refactor.retarget-header", old=self.old, new=self.new)

    def retarget(self) -> None:
        """Drop the edits at the alias's own declarations, at a module's re-export of it and at what a kept re-export
        binds, then refuse overrides and shadowed names and drop duplicate imports."""
        own = set(self.seeds)
        kept: dict[str, list[tuple[int, int]]] = {}
        for path in {e.path for e in self.edits}:
            source = self.snapshot.source(path)
            # A shim keeping its import of the alias keeps every use of it too: the target is not bound there.
            whole = [(0, len(source.text))] if _shim_imports(source, self.old) else []
            kept[path] = [*_reexport_spans(source, self.old), *whole]
        self.edits = [e for e in self.edits if (e.path, e.start) not in own
                      and not any(start <= e.start < end for start, end in kept[e.path])
                      and not self._through_bare_shim(e)]
        self._overrides()
        alias_module = module_name(self.session, self.renamer.resource.path)
        self.edits = [e for edit in self.edits for e in self._import_or_reference(edit, alias_module)]

    def _through_bare_shim(self, edit: TextEdit) -> bool:
        """`edit` is at an import of the alias, or at a reference it binds, from a shim that re-exports the alias without
        binding the target's name, so the target cannot be imported from it."""
        source = self.snapshot.source(edit.path)
        if source.tree is None:
            return False
        parents = {child: node for node in ast.walk(source.tree) for child in ast.iter_child_nodes(node)}
        node = _named_at(source, edit.start, self.old)
        stmt = parents.get(node) if isinstance(node, ast.alias) else _binding_import(parents, node, self.old)
        if not isinstance(stmt, ast.ImportFrom):
            return False
        module = _imported_module(stmt, module_name(self.session, edit.path), edit.path.endswith("__init__.py"))
        return self._bare_shim(module)

    def _bare_shim(self, module: str) -> bool:
        """`module` re-exports the alias by importing it and binds no name of the target's at module level."""
        if module not in self._shims:
            found = self.project.find_module(module) if module else None
            source = self.snapshot.source(found.path) if found is not None else None
            self._shims[module] = (source is not None and source.tree is not None and bool(_shim_imports(source, self.old))
                                   and not any(self.new in _stored(stmt) for stmt in source.tree.body))
        return self._shims[module]

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

    def _import_or_reference(self, edit: TextEdit, alias_module: str) -> list[TextEdit]:
        """`edit`, or what replaces it at a duplicate import; a shadowed reference recorded as a refusal."""
        source = self.snapshot.source(edit.path)
        if source.tree is None:
            return [edit]
        if edit.path not in self._parents:
            self._parents[edit.path] = {child: node for node in ast.walk(source.tree) for child in ast.iter_child_nodes(node)}
        parents = self._parents[edit.path]
        node = _named_at(source, edit.start, self.old)
        if isinstance(node, ast.alias) and isinstance(stmt := parents.get(node), ast.ImportFrom):
            replaced = self._duplicate(source, edit, stmt, node, parents, alias_module)
            if replaced is not None:
                return replaced
            if self._module_binds_other(source, edit.path, alias_module, skip=stmt):
                self._shadowed(source, edit)
        elif isinstance(node, ast.Name):
            use = node

            def accepted(stmt: ast.AST) -> bool:
                return self._binds_target_before(edit.path, stmt, use, parents, alias_module)

            other = edit.path != self.renamer.resource.path and self._module_binds_other(source, edit.path, alias_module)
            if _bound_in_scope(parents, use, self.new, accepted) or other:
                self._shadowed(source, edit)
        return [edit]

    def _binds_target_before(self, rel: str, stmt: ast.AST, use: ast.Name,
                             parents: dict[ast.AST, ast.AST], alias_module: str) -> bool:
        """`stmt` imports the target from the alias's module, and the target is bound before every run of `use`: by
        `stmt` itself, or by an import of the alias in its block that the retarget rewrites."""
        if not (isinstance(stmt, ast.ImportFrom) and self._imports_target(rel, stmt, alias_module)):
            return False
        if _runs_before(parents, stmt, use):
            return True
        return any(_runs_before(parents, s, use) and self._from_alias_module(rel, s, alias_module)
                   and any(a.name == self.old and a.asname is None for a in s.names)
                   for s in _block_of(parents, stmt) if isinstance(s, ast.ImportFrom))

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
        """The module binds the target's name other than by importing it from the alias's module, in any block."""
        assert source.tree is not None

        def accepted(node: ast.AST) -> bool:
            return node is skip or self._imports_target(rel, node, alias_module)

        return any(self.new in _stored(stmt, accepted) for stmt in source.tree.body)

    def _duplicate(
        self, source: SourceFile, edit: TextEdit, stmt: ast.ImportFrom, alias: ast.alias,
        parents: dict[ast.AST, ast.AST], alias_module: str,
    ) -> list[TextEdit] | None:
        """Where the alias's block also imports the target from the alias's module, the later of the two imports
        removed: the alias's import, or the target's while the alias's is rewritten in its place."""
        if alias.asname is not None:
            return None
        rel = edit.path
        targets = [(s, a) for s in _block_of(parents, stmt)
                   if isinstance(s, ast.ImportFrom) and self._from_alias_module(rel, s, alias_module)
                   for a in s.names if a.name == self.new and a.asname in (None, self.new)]
        if not targets:
            return None
        here = source.span(alias)[0]  # pyright: ignore[reportArgumentType]
        if any(source.span(a)[0] < here for _, a in targets):  # pyright: ignore[reportArgumentType]
            return [_alias_removal(source, rel, stmt, alias)]
        later_stmt, later_alias = targets[0]
        return [edit, _alias_removal(source, rel, later_stmt, later_alias)]


def _runs_before(parents: dict[ast.AST, ast.AST], stmt: ast.AST, use: ast.AST) -> bool:
    """`stmt` runs before every run of `use`: a later statement of `stmt`'s own block holds `use`."""
    block = _block_of(parents, stmt)
    later = next((block[k + 1 :] for k, s in enumerate(block) if s is stmt), [])
    node: ast.AST | None = use
    while node is not None:
        if any(s is node for s in later):
            return True
        node = parents.get(node)
    return False


def _block_of(parents: dict[ast.AST, ast.AST], stmt: ast.AST) -> list[ast.stmt]:
    """The statement list holding `stmt`: its parent's `body`, `orelse` or `finalbody`, matched by identity."""
    parent = parents.get(stmt)
    for field in ("body", "orelse", "finalbody"):
        block = getattr(parent, field, None)
        if isinstance(block, list) and any(s is stmt for s in block):
            return block
    return []


def _alias_removal(source: SourceFile, rel: str, stmt: ast.ImportFrom, alias: ast.alias) -> TextEdit:
    """The removal of `alias` from its import: the whole statement when it is the only name."""
    if len(stmt.names) == 1:
        return _statement_removal(source, rel, stmt)
    spans = [source.span(a) for a in stmt.names]  # pyright: ignore[reportArgumentType]
    i = next(k for k, a in enumerate(stmt.names) if a is alias)
    start, end = (spans[i][0], spans[i + 1][0]) if i + 1 < len(spans) else (spans[i - 1][1], spans[i][1])
    return TextEdit(path=rel, start=start, end=end, new_text="")


def _shim_imports(source: SourceFile, name: str) -> list[ast.alias]:
    """A module's imports binding `name` at module level, when its `__all__` lists `name`."""
    if source.tree is None or not any(isinstance(n, ast.Constant) and n.value == name
                                      for stmt in source.tree.body if _assigns_all(stmt) for n in ast.walk(stmt)):
        return []
    return [a for stmt in source.tree.body if isinstance(stmt, (ast.Import, ast.ImportFrom)) for a in stmt.names
            if (a.asname or a.name.split(".")[-1]) == name]


def _binding_import(parents: dict[ast.AST, ast.AST], node: ast.AST | None, name: str) -> ast.AST | None:
    """The `from ... import` binding a bare `name` at `node`, looked up through the enclosing function scopes to the
    module; None when a nearer scope binds it otherwise."""
    if not isinstance(node, ast.Name):
        return None
    scope = parents.get(node)
    while scope is not None:
        if isinstance(scope, (ast.Module, *_FUNCTIONS)):
            body = scope.body if isinstance(scope.body, list) else []
            imported = [s for s in _walk_scope(body) if isinstance(s, ast.ImportFrom)
                        and any((a.asname or a.name) == name for a in s.names)]
            if imported:
                return imported[0]
            if any(name in _stored(s) for s in body):
                return None
        scope = parents.get(scope)
    return None


def _walk_scope(body: list[ast.stmt]) -> Iterator[ast.stmt]:
    """The statements of a scope's body, compound statements entered, nested functions and classes not."""
    for stmt in body:
        yield stmt
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        blocks = [getattr(stmt, field, []) for field in ("body", "orelse", "finalbody")]
        blocks += [clause.body for clause in [*getattr(stmt, "handlers", []), *getattr(stmt, "cases", [])]]
        for block in blocks:
            yield from _walk_scope(block)


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
