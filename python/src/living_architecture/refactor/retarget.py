"""`retarget`: the rename of an alias to its target's name without the alias's own declaration and its re-export
sites. Every rewritten name stays bound: an import of the alias is re-pointed, else the target is imported from its
home; a name nothing can bind refuses."""

from __future__ import annotations

import ast
import builtins
from collections.abc import Callable, Iterator

from pydantic import BaseModel, ConfigDict
from typing_extensions import override

from living_architecture.contract import message
from living_architecture.refactor.carve_outs import CarveOuts
from living_architecture.refactor.entry_location import Entry, EntryLocator
from living_architecture.refactor.locators import RefactorError
from living_architecture.refactor.outcomes import Finding
from living_architecture.refactor.python_source import SourceFile, every_parameter, split_lines
from living_architecture.refactor.rename_union import RenameOptions, RenameResult, Session, SymbolRename
from living_architecture.refactor.static_resolver import Value, node_key
from living_architecture.refactor.text_edits import TextEdit

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_BUILTINS = frozenset(dir(builtins))
_SHADOWED = "refactor.retarget-shadowed"
_DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Assign, ast.AnnAssign)

_INIT = "__init__.py"

Location = tuple[str, int]
Parents = dict[ast.AST, ast.AST]


class TargetHome(BaseModel):
    """A module alias's target: the module its alias's module imports it from (or declares it in), the name that
    module exports it by, the name written for it, and its definition."""

    model_config = ConfigDict(frozen=True)

    module: str
    exported: str
    local: str
    definition: Location | None


class ImportNeed(BaseModel):
    """`local` bound to the target in the block of `anchor` (when `bind`); `leaving`, an import of the alias in
    `anchor`, dropped from it; `duplicates`, later imports of the target the added one makes redundant."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    path: str
    anchor: ast.stmt
    home: TargetHome
    local: str
    bind: bool
    entry: int = 0
    leaving: ast.alias | None = None
    duplicates: tuple[ast.alias, ...] = ()


def module_name(session: Session, rel: str) -> str:
    return session.modname(rel)


def package_of(session: Session, rel: str) -> str:
    """The package a relative import in `rel` is resolved against."""
    name = module_name(session, rel)
    return name if rel.endswith(_INIT) else name.rpartition(".")[0]


def imported_module(session: Session, rel: str, stmt: ast.ImportFrom) -> str:
    """The absolute name of the module `stmt` imports from."""
    if stmt.level == 0:
        return stmt.module or ""
    parts = package_of(session, rel).split(".")
    parts = parts[: len(parts) - (stmt.level - 1)]
    return ".".join([*parts, *([stmt.module] if stmt.module else [])])


def module_file(session: Session, module: str) -> str | None:
    """The project file of module `module`, a package's `__init__.py`."""
    found = session.layout.module_file(module)
    return session.rel(found) if found is not None else None


def definition(entry: Entry) -> Location | None:
    """Where an entry's symbol is first declared, imports followed; None for a module or outside the project."""
    return None if entry.kind in ("site", "module") or not entry.sites else (str(entry.key[1]), int(entry.key[2]))  # pyright: ignore[reportArgumentType]


def attribute_definition(locator: EntryLocator, module: str, name: str) -> Location | None:
    """Where the attribute `name` of module `module` is defined."""
    try:
        found = locator.value(locator.resolver.member(module, name), name)
    except RefactorError:
        return None
    return definition(found) if found is not None else None


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


def _bound_in_scope(parents: Parents, node: ast.AST, name: str, accepted: Callable[[ast.AST], bool]) -> bool:
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

    def __init__(self, session: Session, entry: Entry, target: str, options: RenameOptions, *,
                 site: tuple[str, int], locator: EntryLocator, line: int, home: TargetHome | None = None,
                 own: Location | None = None, original: str | None = None, index: int = 0,
                 carves: CarveOuts | None = None) -> None:
        super().__init__(session, entry, target, options, site=site, locator=locator, carves=carves)
        self.check_names = False
        self.line = line
        self.home = home
        self.own = own
        self.original = original or target
        self.index = index
        self.refusals: list[Finding] = []
        self.needs: list[ImportNeed] = []
        self.held: list[TextEdit] = []
        self.imports: list[TextEdit] = []
        self._parents: dict[str, Parents] = {}
        self._exports: dict[str, bool] = {}
        self._definitions: dict[tuple[str, str], Location | None] = {}

    @override
    def header(self) -> str:
        return message("refactor.retarget-header", old=self.old, new=self.new)

    @override
    def result(self, entry: int, target: str | None, kept: list[TextEdit]) -> RenameResult:
        out = super().result(entry, target, kept)
        out.refusals = self.refusals
        return out

    def parents(self, rel: str) -> Parents:
        if rel not in self._parents:
            tree = self.snapshot.source(rel).tree
            self._parents[rel] = {} if tree is None else {c: n for n in ast.walk(tree) for c in ast.iter_child_nodes(n)}
        return self._parents[rel]

    def retarget(self, kept: Callable[[TextEdit], bool]) -> None:
        """Drop the edits at the alias's own declaration, at its re-export sites and the `kept` ones; refuse overrides,
        shadowed and unbound names; record the imports the rest need."""
        own = set(self.seeds) | ({self.own} if self.own is not None else set())
        spans = {path: _reexport_spans(self.snapshot.source(path), self.old) for path in {e.path for e in self.edits}}
        edits = [e for e in self.edits if (e.path, e.start) not in own and not any(s <= e.start < t for s, t in spans[e.path])]
        self._overrides()
        live = [e for e in edits if not kept(e)]
        self.held = [e for e in edits if e not in live]
        if self.home is None:
            self.edits = live
            return
        held = {id(b[1]) for e in edits if e not in live and (b := self._binding(e)) is not None}
        self.edits = self._decide(live, held)

    def _binding(self, edit: TextEdit) -> tuple[ast.ImportFrom, ast.alias] | None:
        """The import binding the bare name at `edit`."""
        node = _named_at(self.snapshot.source(edit.path), edit.start, self.old)
        return _binding_of(self.parents(edit.path), node, self.old) if isinstance(node, ast.Name) else None

    def _decide(self, live: list[TextEdit], held: set[int]) -> list[TextEdit]:
        """Each live edit kept, replaced or refused by the site it is at; the imports of the alias other than the
        held ones re-pointed or left. An import that would bind the target's name over a builtin is refused unless a
        use in its file already is."""
        sites = {id(a) for e in live if isinstance(a := _named_at(self.snapshot.source(e.path), e.start, self.old), ast.alias)}
        moving = sites - held
        out: list[TextEdit] = []
        rebinding: list[TextEdit] = []
        for edit in live:
            source = self.snapshot.source(edit.path)
            node = _named_at(source, edit.start, self.old) if source.tree is not None else None
            if isinstance(node, ast.alias):
                out += self._alias_site(source, edit, node, moving, rebinding)
            elif isinstance(node, ast.Name):
                out.append(edit)
                self._use(edit, node, moving)
            elif source.tree is not None and isinstance(attr := _attribute_at(source, edit.start, self.old), ast.Attribute):
                out += self._attribute(edit, attr)
            else:
                out.append(edit)
        self._refuse_rebinding(rebinding)
        return out

    def _alias_site(self, source: SourceFile, edit: TextEdit, alias: ast.alias, moving: set[int],
                    rebinding: list[TextEdit]) -> list[TextEdit]:
        """An import of the alias re-pointed when it moves; recorded in `rebinding` when that binds the target's name
        where it means a builtin."""
        if id(alias) not in moving:
            return []
        if alias.asname is None and self._builtin_at(source, alias, self.parents(edit.path)):
            rebinding.append(edit)
        return self._import_site(edit, alias)

    def _refuse_rebinding(self, rebinding: list[TextEdit]) -> None:
        """Each import in `rebinding` refused, unless a site in its file already is."""
        refused = {f.path for f in self.refusals}
        for edit in rebinding:
            if edit.path not in refused:
                self._refuse(edit, _SHADOWED, name=self.new)

    def _import_site(self, edit: TextEdit, alias: ast.alias) -> list[TextEdit]:
        """An import of the alias from a module exporting the target re-pointed to it there; from any other module,
        the alias left and the target imported from its home."""
        assert self.home is not None
        source = self.snapshot.source(edit.path)
        parents = self.parents(edit.path)
        stmt = parents[alias]
        assert isinstance(stmt, ast.ImportFrom)
        if self._module_binds_other(source, edit.path, skip=stmt):
            self._refuse(edit, _SHADOWED, name=self.new)
        if self._exported_by(imported_module(self.session, edit.path, stmt)):
            return self._duplicate(source, edit, stmt, alias, parents) or [edit]
        self._need(edit.path, stmt, alias.asname, alias)
        return []

    def _need(self, rel: str, anchor: ast.stmt, asname: str | None, leaving: ast.alias | None) -> None:
        assert self.home is not None
        bound, later = self._bindings(rel, anchor, asname or self.original, self.parents(rel))
        self.needs.append(ImportNeed(path=rel, anchor=anchor, home=self.home, local=asname or self.new, bind=not bound,
                                     entry=self.index, leaving=leaving, duplicates=tuple(later)))

    def _use(self, edit: TextEdit, use: ast.Name, moving: set[int]) -> None:
        """A bare use: the target imported where its binding import stays or is a star import not binding the
        target; refused where the target's name means something else."""
        assert self.home is not None
        parents = self.parents(edit.path)
        binding = _binding_of(parents, use, self.old)
        anchor: ast.ImportFrom | None = None
        if binding is not None and binding[1].name == "*":
            anchor = None if self._star_binds(imported_module(self.session, edit.path, binding[0])) else binding[0]
        elif binding is not None and id(binding[1]) not in moving:
            anchor = binding[0]
        if anchor is not None:
            self._need(edit.path, anchor, None, None)

        def accepted(stmt: ast.AST) -> bool:
            return self._binds_target_before(edit.path, stmt, use, parents)

        source = self.snapshot.source(edit.path)
        other = edit.path != self.entry.rel and self._module_binds_other(source, edit.path)
        if _bound_in_scope(parents, use, self.new, accepted) or other or self._builtin_at(source, use, parents):
            self._refuse(edit, _SHADOWED, name=self.new)

    def _attribute(self, edit: TextEdit, attr: ast.Attribute) -> list[TextEdit]:
        """`MOD.ALIAS` rewritten where module `MOD` binds the target's name to the target; refused otherwise."""
        assert self.home is not None
        module = self._receiver_module(edit.path, attr)
        if module is None:
            return [edit]
        if self._is_target(module[0], self.original):
            return [edit]
        self._refuse(edit, "refactor.retarget-unbound", module=module[1], name=self.new)
        return []

    def _receiver_module(self, rel: str, attr: ast.Attribute) -> tuple[str, str] | None:
        """The project module `attr`'s receiver names, by Python's scoping: its name and its file."""
        own = self.locator.module(rel)
        scope = self.locator.load_scopes(rel, own).get(id(attr.value)) if own is not None else None
        if own is None or scope is None:
            return None
        value = self._assigned(self.locator.resolver.resolve(own, scope, attr.value))
        found = self.locator.folders.file(value[1]) if value is not None and value[0] == "module" else None
        path = self.session.rel(found[0]) if found is not None else None
        return (value[1], path) if value is not None and path is not None else None

    def _assigned(self, value: Value) -> Value:
        """`value`, while it is a name assigned a plain name or attribute (`mirror = facade`), followed to that."""
        seen: set[Value] = set()
        while value is not None and value[0] == "decl" and value not in seen:
            seen.add(value)
            found = self.locator.resolver.declaration(value)
            at = self.locator.module_at(found[0]) if found is not None else None
            if found is None or at is None:
                return value
            rel, own = at
            node = own.binder.decls.get(node_key(found[1]))
            stmt = self.snapshot.source(rel).parent(node) if node is not None else None
            if not (isinstance(stmt, ast.Assign) and stmt.targets == [node] and isinstance(stmt.value, (ast.Name, ast.Attribute))):
                return value
            scope = self.locator.load_scopes(rel, own).get(id(stmt.value))
            if scope is None:
                return value
            value = self.locator.resolver.resolve(own, scope, stmt.value)
        return value

    def _refuse(self, edit: TextEdit, template: str, **values: str) -> None:
        line = self.snapshot.source(edit.path).line(edit.start)
        self.refusals.append(Finding(path=edit.path, line=line, col=edit.start, text=message(template, path=edit.path, line=line, **values)))

    def _overrides(self) -> None:
        if not self.member:
            return
        hierarchy = self.located_hierarchy()
        rel = self.entry.rel
        own = next((d.cls for d in self._declarations if d.rel == rel and d.line == self.line), None)
        for d in self._declarations:
            if (d.rel, d.start) in hierarchy and not (d.rel == rel and d.cls == own):
                text = message("refactor.retarget-override", path=d.rel, line=d.line, cls=d.cls, name=self.old)
                self.refusals.append(Finding(path=d.rel, line=d.line, col=d.start, text=text))

    # ---- what binds the target

    def _attribute_definition(self, module: str, name: str) -> Location | None:
        if (module, name) not in self._definitions:
            self._definitions[module, name] = attribute_definition(self.locator, module, name)
        return self._definitions[module, name]

    def _is_target(self, module: str, name: str) -> bool:
        assert self.home is not None
        return self.home.definition is not None and self._attribute_definition(module, name) == self.home.definition

    def _module_source(self, module: str) -> SourceFile | None:
        found = module_file(self.session, module)
        return self.snapshot.source(found) if found is not None else None

    def _exported_by(self, module: str) -> bool:
        """`module` exports the target under its name: declares it, lists it in `__all__`, or imports it as itself."""
        if module not in self._exports:
            source = self._module_source(module)
            tree = source.tree if source is not None else None
            name = self.original
            exported = tree is not None and source is not None and (
                any(name in _stored(s) for s in tree.body if not isinstance(s, (ast.Import, ast.ImportFrom)))
                or name in _all_names(source)
                or any(a.name == a.asname == name for s in tree.body if isinstance(s, ast.ImportFrom) for a in s.names))
            self._exports[module] = exported and self._is_target(module, name)
        return self._exports[module]

    def _star_binds(self, module: str) -> bool:
        """A star import of `module` binds the target's name to the target."""
        source = self._module_source(module)
        if source is None or source.tree is None:
            return False
        name = self.original
        if source.all_statements:
            listed = name in _all_names(source)
        else:
            listed = not name.startswith("_") and any(name in _stored(s) for s in source.tree.body)
        return listed and self._is_target(module, name)

    def _binds_local(self, rel: str, stmt: ast.stmt, local: str) -> bool:
        """`stmt` binds `local` to the target."""
        assert self.home is not None
        if isinstance(stmt, ast.ImportFrom):
            module = imported_module(self.session, rel, stmt)
            named = [a for a in stmt.names if a.name not in ("*", self.old)]
            return any((a.asname or a.name) == local and self._is_target(module, a.name) for a in named) or (
                any(a.name == "*" for a in stmt.names) and local == self.original and self._star_binds(module))
        return isinstance(stmt, _DEFINITIONS) and (rel, stmt.lineno) == self.home.definition and local in _stored(stmt)

    def _bindings(self, rel: str, anchor: ast.stmt, local: str, parents: Parents) -> tuple[bool, list[ast.alias]]:
        """Whether `anchor` or an earlier statement of its block, or of a block enclosing it within the function that
        binds `local`, binds `local` to the target; else the later imports of `anchor`'s block that do."""
        if self._binds_local(rel, anchor, local):
            return True, []
        stmt: ast.AST | None = anchor
        while isinstance(stmt, ast.stmt):
            for s in block_of(parents, stmt):
                if s is stmt:
                    break
                if self._binds_local(rel, s, local):
                    return True, []
            stmt = _enclosing_statement(parents, stmt)
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and _binds(stmt, local, lambda _: False):
                break
        block = block_of(parents, anchor)
        later = block[next(k for k, s in enumerate(block) if s is anchor) + 1 :]
        return False, [a for s in later if isinstance(s, ast.ImportFrom) and self._binds_local(rel, s, local)
                       for a in s.names if (a.asname or a.name) == local]

    def _binds_target_before(self, rel: str, stmt: ast.AST, use: ast.Name, parents: Parents) -> bool:
        """`stmt` imports the target under its name, and the target is bound before every run of `use`: by `stmt`
        itself, or by an import of the alias in its block."""
        if not (isinstance(stmt, ast.stmt) and self._binds_local(rel, stmt, self.original)):
            return False
        if _runs_before(parents, stmt, use):
            return True
        return any(_runs_before(parents, s, use) and any(a.name == self.old and a.asname is None for a in s.names)
                   for s in block_of(parents, stmt) if isinstance(s, ast.ImportFrom))

    def _builtin_at(self, source: SourceFile, node: ast.AST, parents: Parents) -> bool:
        """The target's name means a builtin at `node`: no enclosing scope nor the module binds it."""
        assert source.tree is not None
        if self.new not in _BUILTINS or _bound_in_scope(parents, node, self.new, lambda _: False):
            return False
        return not any(self.new in _stored(stmt) for stmt in source.tree.body)

    def _module_binds_other(self, source: SourceFile, rel: str, skip: ast.AST | None = None) -> bool:
        """The module binds the target's name other than to the target, in any block."""
        assert source.tree is not None

        def accepted(node: ast.AST) -> bool:
            return node is skip or (isinstance(node, ast.stmt) and self._binds_local(rel, node, self.original))

        return any(self.new in _stored(stmt, accepted) for stmt in source.tree.body)

    def _duplicate(self, source: SourceFile, edit: TextEdit, stmt: ast.ImportFrom, alias: ast.alias,
                   parents: Parents) -> list[TextEdit] | None:
        """Where the alias's block also imports the target from the same module, the later of the two imports
        removed: the alias's import, or the target's while the alias's is rewritten in its place."""
        if alias.asname is not None:
            return None
        rel = edit.path
        module = imported_module(self.session, rel, stmt)
        targets = [(s, a) for s in block_of(parents, stmt)
                   if isinstance(s, ast.ImportFrom) and imported_module(self.session, rel, s) == module
                   for a in s.names if a.name == self.new and a.asname in (None, self.new)]
        if not targets:
            return None
        here = source.span(alias)[0]  # pyright: ignore[reportArgumentType]
        if any(source.span(a)[0] < here for _, a in targets):  # pyright: ignore[reportArgumentType]
            return aliases_removal(source, rel, stmt, {id(alias)})
        later_stmt, later_alias = targets[0]
        return [edit, *aliases_removal(source, rel, later_stmt, {id(later_alias)})]


def _runs_before(parents: Parents, stmt: ast.AST, use: ast.AST) -> bool:
    """`stmt` runs before every run of `use`: a later statement of `stmt`'s own block holds `use`."""
    block = block_of(parents, stmt)
    later = next((block[k + 1 :] for k, s in enumerate(block) if s is stmt), [])
    node: ast.AST | None = use
    while node is not None:
        if any(s is node for s in later):
            return True
        node = parents.get(node)
    return False


def block_of(parents: Parents, stmt: ast.AST) -> list[ast.stmt]:
    """The statement list holding `stmt`: its parent's `body`, `orelse` or `finalbody`, matched by identity."""
    parent = parents.get(stmt)
    for field in ("body", "orelse", "finalbody"):
        block = getattr(parent, field, None)
        if isinstance(block, list) and any(s is stmt for s in block):
            return block
    return []


def _enclosing_statement(parents: Parents, stmt: ast.AST) -> ast.AST | None:
    """The compound statement or function whose block holds `stmt`; None at module level."""
    node = parents.get(stmt)
    while node is not None and not isinstance(node, ast.stmt):
        node = parents.get(node)
    return node


def aliases_removal(source: SourceFile, rel: str, stmt: ast.ImportFrom, removed: set[int]) -> list[TextEdit]:
    """The removal of the `removed` names from an import: the whole statement when no name is left."""
    names = stmt.names
    if all(id(a) in removed for a in names):
        return [statement_removal(source, rel, stmt)]
    spans = [source.span(a) for a in names]  # pyright: ignore[reportArgumentType]
    edits: list[TextEdit] = []
    i = 0
    while i < len(names):
        if id(names[i]) not in removed:
            i += 1
            continue
        j = i
        while j < len(names) and id(names[j]) in removed:
            j += 1
        start, end = (spans[i][0], spans[j][0]) if j < len(names) else (spans[i - 1][1], spans[j - 1][1])
        edits.append(TextEdit(path=rel, start=start, end=end, new_text=""))
        i = j
    return edits


def _binding_of(parents: Parents, node: ast.AST | None, name: str) -> tuple[ast.ImportFrom, ast.alias] | None:
    """The `from ... import` binding a bare `name` at `node` (a star import where nothing else does), looked up
    through the enclosing function scopes to the module; None when a nearer scope binds it otherwise."""
    scope = parents.get(node) if node is not None else None
    while scope is not None:
        if isinstance(scope, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef)):
            imports = [s for s in _walk_scope(scope.body) if isinstance(s, ast.ImportFrom)]
            found = next(((s, a) for s in imports for a in s.names if (a.asname or a.name) == name), None)
            if found is not None:
                return found
            if any(name in _stored(s) for s in scope.body):
                return None
            stars = [(s, a) for s in imports for a in s.names if a.name == "*"]
            if stars and isinstance(scope, ast.Module):
                return stars[-1]
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


def _all_names(source: SourceFile) -> set[str]:
    """The names a module's `__all__` lists."""
    return {str(n.value) for n in source.all_strings()}


def _reexport_spans(source: SourceFile, name: str) -> list[tuple[int, int]]:
    """Where a module re-exports `name` (its `__all__` lists it): the `__all__` strings and its imports of `name`."""
    if source.tree is None:
        return []
    names = [n for n in source.all_strings() if n.value == name]
    if not names:
        return []
    imports = [a for stmt in source.tree.body if isinstance(stmt, (ast.Import, ast.ImportFrom)) for a in stmt.names
               if (a.asname or a.name.split(".")[-1]) == name]
    return [source.span(n) for n in [*names, *imports]]  # pyright: ignore[reportArgumentType]


def statement_removal(source: SourceFile, rel: str, stmt: ast.stmt) -> TextEdit:
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
    if source.tree is None:
        return None
    for node in source.nodes:
        if isinstance(node, ast.Name) and node.id == name and source.span(node)[0] == offset:
            return node
        if isinstance(node, ast.alias) and node.name == name and source.offset(node.lineno, node.col_offset) == offset:
            return node
    return None


def _attribute_at(source: SourceFile, offset: int, name: str) -> ast.Attribute | None:
    """The `ast.Attribute` whose attribute `name` starts at `offset`."""
    assert source.tree is not None
    return next((n for n in source.nodes if isinstance(n, ast.Attribute) and n.attr == name
                 and (span := source.name_span(n)) is not None and span[0] == offset), None)
