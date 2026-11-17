"""A Python rename's entry located without rope: the declaration at a locator's site from the syntax tree, la's static
resolver, else the checker's definition; its kind and its canonical key."""

from __future__ import annotations

import ast
import keyword
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from living_architecture.refactor.bindings import bound_at
from living_architecture.refactor.locators import Locator, RefactorError, cannot_rename, resolve
from living_architecture.refactor.members import member_declarations, receiver_stores
from living_architecture.refactor.patch_targets import SourceFolders
from living_architecture.refactor.python_project import ProjectLayout, Snapshot
from living_architecture.refactor.python_source import SourceFile, dotted_segments, name_end, nfkc
from living_architecture.refactor.static_resolver import Module, Resolver, Scope, Value, node_key

# The checker's `definition` at a site of a project file: each declaration's file and offset.
Definitions = Callable[[str, int], list[tuple[Path, int]]]
Kind = Literal["name", "parameter", "local", "method", "member", "module", "site"]
# A declaration: a project-relative path and the offset of the name it declares.
Site = tuple[str, int]

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPE_KINDS: dict[str, Kind] = {"module": "name", "function": "local", "comprehension": "local", "annotation": "local"}


class Entry(BaseModel):
    """A located entry: its kind, canonical key and old name, the file it was located in, the declarations of its
    symbol in source order, a module rename's module (a file, or a package's directory), a parameter's function, and
    whether it is an import binding matched by binding."""

    model_config = ConfigDict(frozen=True)

    kind: Kind
    key: tuple[object, ...]
    name: str
    rel: str
    sites: tuple[Site, ...] = ()
    module: str | None = None
    function: Site | None = None
    binding: bool = False


def _name_char(ch: str) -> bool:
    return ("_" + ch).isidentifier()


class EntryLocator:
    """Locates entries in the project at `root`; `definitions` is asked only where the static resolver gives no
    answer."""

    def __init__(self, root: Path, definitions: Definitions, snapshot: Snapshot | None = None,
                 layout: ProjectLayout | None = None) -> None:
        self.root = root.resolve()
        self.snapshot = snapshot or Snapshot(self.root)
        self.layout = layout or ProjectLayout(self.root)
        self.folders = SourceFolders([*self.layout.source_folders(), self.root])
        self.resolver = Resolver(self.folders, self._read)
        self.definitions = definitions
        self._modules: dict[str, Module | None] = {}
        self._scopes: dict[str, dict[int, Scope]] = {}

    # ---- files

    def rel(self, path: Path) -> str | None:
        resolved = path.resolve() if path.is_absolute() else (self.root / path).resolve()
        return resolved.relative_to(self.root).as_posix() if resolved.is_relative_to(self.root) else None

    def _read(self, path: Path) -> str:
        rel = self.rel(path)
        return self.snapshot.text(rel) if rel is not None else path.read_text(encoding="utf-8")

    def module(self, rel: str) -> Module | None:
        """`rel`'s static model, registered with the resolver under its module name."""
        if rel not in self._modules:
            source = self.snapshot.source(rel)
            found: Module | None = None
            if source.tree is not None:
                dotted = self.layout.modname(self.root / rel)
                found = Module(source.tree, dotted.split("."), Path(rel).stem == "__init__", self.root / rel)
                self.resolver.modules.setdefault(dotted, found)
            self._modules[rel] = found
        return self._modules[rel]

    def module_at(self, module: Module) -> tuple[str, Module] | None:
        """A resolver module's file, and the model of that file the locator reads its offsets in."""
        rel = self.rel(module.path) if module.path is not None else None
        own = self.module(rel) if rel is not None else None
        return (rel, own) if rel is not None and own is not None else None

    def load_scopes(self, rel: str, module: Module) -> dict[int, Scope]:
        """The scope of each name or attribute read in `rel`, annotations included."""
        if rel not in self._scopes:
            found = {id(node): scope for node, scope in module.binder.loads}
            for expr, scope in module.binder.annotations:
                for node in ast.walk(expr):
                    if isinstance(node, (ast.Name, ast.Attribute)):
                        found.setdefault(id(node), scope)
            self._scopes[rel] = found
        return self._scopes[rel]

    # ---- the entry

    def file_module(self, rel: str) -> Entry:
        """The rename of the Python module `rel` itself; a package's `__init__.py` names the package."""
        path = Path(rel)
        package = path.stem == "__init__"
        return _module(rel, path.parent.as_posix() if package else rel, path.parent.name if package else path.stem, "")

    def locate(self, rel: str, locator: Locator) -> Entry:
        """The entry `locator` names in `rel`."""
        offset, _ = resolve(locator, self.snapshot.source(rel), rel)
        return self.at(rel, offset)

    def at(self, rel: str, offset: int, *, follow: bool = False) -> Entry:
        """The entry at `offset` of `rel`: the declaration its identifier binds, else the one it reads; with `follow`,
        an import alias or re-export is followed to what it imports."""
        source = self.snapshot.source(rel)
        text = source.text
        if offset >= len(text) or not _name_char(text[offset]):
            raise cannot_rename()
        start = offset
        while start > 0 and _name_char(text[start - 1]):
            start -= 1
        word = text[start : name_end(text, offset)]
        module = self.module(rel)
        if not word.isidentifier() or keyword.iskeyword(word) or module is None:
            raise cannot_rename()
        name = nfkc(word)
        declared = self._binding(rel, module, start, name, follow=follow)
        if declared is not None:
            return declared
        dotted = self._import_path(module, self.snapshot.source(rel), start)
        return self._module_entry(rel, dotted, name) if dotted is not None else self._reference(rel, module, start, name)

    @staticmethod
    def _import_path(module: Module, source: SourceFile, start: int) -> str | None:
        """The module an import's written module path names up to its identifier at `start`."""
        for node in source.of_type(ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                spans = dotted_segments(source.text, *source.span(alias))[: len(parts)]  # pyright: ignore[reportArgumentType]
                hit = next((i for i, span in enumerate(spans) if span[0] == start), None)
                if hit is not None:
                    return ".".join(parts[: hit + 1])
        for node in source.of_type(ast.ImportFrom):
            absolute = module.binder.from_module(node)
            hit = next((i for i, span in enumerate(source.from_path(node)) if span[0] == start), None)
            if hit is not None and absolute is not None and node.module is not None:
                parts = absolute.split(".")
                return ".".join(parts[: len(parts) - len(node.module.split(".")) + hit + 1])
        return None

    # ---- bindings

    def _binding(self, rel: str, module: Module, start: int, name: str, *, follow: bool = False) -> Entry | None:
        """The entry of the binding whose identifier starts at `start`, or None when it is not one."""
        source = self.snapshot.source(rel)
        for scope, bound, node in module.binder.bound:
            if bound == name and bound_at(source, node, bound) == start:
                if isinstance(node, ast.alias):
                    return self._import(rel, module, scope, name, node, start, follow=follow)
                return self._group(rel, rel, module, scope.owner(name), name)
        owner = self._declared_scope(rel, module, start, name)
        if owner is not None:
            return self._group(rel, rel, module, owner, name)
        cls = self._self_store(source, start, name)
        return self._members(rel, rel, source, cls, name) if cls is not None else None

    def _declared_scope(self, rel: str, module: Module, start: int, name: str) -> Scope | None:
        """The scope a `global` or `nonlocal` statement naming `name` at `start` binds it in."""
        source = self.snapshot.source(rel)
        for node in source.nodes:
            if not isinstance(node, (ast.Global, ast.Nonlocal)) or name not in node.names:
                continue
            span = source.word(*source.span(node), name)
            if span is None or span[0] != start:
                continue
            up = source.parent(node)
            while up is not None and not isinstance(up, (*_FUNCTIONS, ast.ClassDef)):
                up = source.parent(up)
            scope = module.binder.inner.get(id(up), module.scope) if up is not None else module.scope
            return scope.owner(name) if isinstance(node, ast.Nonlocal) else module.scope
        return None

    @staticmethod
    def _self_store(source: SourceFile, start: int, name: str) -> ast.ClassDef | None:
        """The class of the method whose `self.NAME` store's name starts at `start`."""
        for cls in source.of_type(ast.ClassDef):
            for method in (s for s in ast.walk(cls) if isinstance(s, _FUNCTIONS) and source.parent(s) is cls):
                if any(t.attr == name and (span := source.name_span(t)) is not None and span[0] == start
                       for t in receiver_stores(method)):
                    return cls
        return None

    def _import(self, rel: str, module: Module, scope: Scope, name: str, alias: ast.alias, start: int, *,
                follow: bool) -> Entry:
        """An import binding: the module it binds, else itself for an alias or re-export, else what it imports."""
        stmt = self.snapshot.source(rel).parent(alias)
        if isinstance(stmt, ast.Import):
            value: Value = ("module", alias.name if alias.asname else name)
        else:
            assert isinstance(stmt, ast.ImportFrom)
            value = self.resolver.member(module.binder.from_module(stmt), alias.name)
        if value is not None and value[0] == "module":
            return self._module_entry(rel, value[1], name)
        owner = scope.owner(name)
        aliased = alias.asname is not None and alias.asname != alias.name
        exported = owner.kind == "module" and (alias.asname == alias.name or name in (module.all_names or ()))
        if (aliased or exported) and not follow:
            line = self.snapshot.source(rel).line(start)
            kind = _SCOPE_KINDS.get(owner.kind, "local")
            return Entry(kind=kind, key=(kind, rel, line, name), name=name, rel=rel, sites=((rel, start),), binding=True)
        found = self.value(value, name, rel)
        return found if found is not None else self._checked(rel, start, name)

    # ---- groups

    def group_at(self, rel: str, module: Module, node: ast.AST, name: str) -> Entry | None:
        """The entry of the declaration group the binding `node` of `name` belongs to; None when it has none."""
        scope = next((s for s, bound, n in module.binder.bound if n is node and bound == name), None)
        if scope is None:
            return None
        try:
            return self._group(rel, rel, module, scope.owner(name), name)
        except RefactorError:
            return None

    def _group(self, located: str, rel: str, module: Module, owner: Scope, name: str) -> Entry:
        """The entry of every declaration of `name` that binds in `owner`."""
        source = self.snapshot.source(rel)
        if owner.kind == "class":
            return self._members(located, rel, source, module.binder.class_nodes[owner], name)
        nodes = [(bound_at(source, node, name), node) for scope, bound, node in module.binder.bound
                 if bound == name and scope.owner(name) is owner]
        declared = sorted((start, node) for start, node in nodes if start is not None)
        if not declared:
            raise cannot_rename()
        start, first = declared[0]
        kind: Kind = "parameter" if isinstance(first, ast.arg) else _SCOPE_KINDS.get(owner.kind, "local")
        function = _function(rel, source, first) if isinstance(first, ast.arg) else None
        # Two lambdas or comprehensions on one line bind separate groups.
        inner = (start,) if owner.kind != "module" else ()
        return Entry(kind=kind, key=(kind, rel, source.line(start), name, *inner), name=name, rel=located,
                     sites=tuple((rel, s) for s, _ in declared), function=function)

    def _members(self, located: str, rel: str, source: SourceFile, cls: ast.ClassDef, name: str) -> Entry:
        """The entry of member `name` of class `cls`: its declarations in the class body and its methods."""
        spans = sorted((span[0], node) for node in member_declarations(cls, name)
                       if (span := source.name_span(node) or _bound_span(source, node, name)) is not None)
        if not spans:
            raise cannot_rename()
        start, first = spans[0]
        kind: Kind = "method" if isinstance(first, _FUNCTIONS) else "member"
        return Entry(kind=kind, key=(kind, rel, source.line(start), name), name=name, rel=located,
                     sites=tuple((rel, s) for s, _ in spans))

    # ---- references

    def _reference(self, rel: str, module: Module, start: int, name: str) -> Entry:
        """The entry of the declaration the read at `start` resolves to: statically, else by the checker."""
        source = self.snapshot.source(rel)
        node = source.name_at(start)
        scope = self.load_scopes(rel, module).get(id(node)) if node is not None else None
        if isinstance(node, ast.expr) and scope is not None:
            found = self.value(self.resolver.resolve(module, scope, node), name, rel)
            if found is not None:
                return found
        return self._checked(rel, start, name)

    def value(self, value: Value, name: str, rel: str = "") -> Entry | None:
        """The entry of a static value: a project declaration or module; a library member keys by nothing here."""
        if value is None or value[0] == "typing":
            return None
        if value[0] == "module":
            return self._module_entry(rel, value[1], name)
        found = self.resolver.declaration(value)
        at = self.module_at(found[0]) if found is not None else None
        if found is None or at is None:
            return None
        decl_rel, own = at
        node = own.binder.decls.get(node_key(found[1]))
        scope = own.binder.enclosing.get(node_key(found[1]))
        if node is None or scope is None:
            return None
        if scope.kind == "annotation" and scope.parent is not None:
            scope = scope.parent
        declared = node.name if isinstance(node, (*_FUNCTIONS, ast.ClassDef)) else getattr(node, "id", name)
        return self._group(rel, decl_rel, own, scope.owner(declared), declared)

    def _module_entry(self, rel: str, dotted: str, name: str) -> Entry:
        """A module rename: of the project module's file or package directory, else of a library module's alias."""
        found = self.folders(dotted)
        module_rel = self.rel(found[0]) if found is not None else None
        if found is not None and found[1] and module_rel is not None:
            module_rel = Path(module_rel).parent.as_posix()
        return _module(rel, module_rel, name, dotted)

    def _checked(self, rel: str, start: int, name: str) -> Entry:
        """The entry of the declarations the checker resolves the site to; the site itself for a library's."""
        found = self.definitions(rel, start)
        if not found:
            raise cannot_rename()
        project = [(r, s) for path, s in found if (r := self.rel(path)) is not None]
        if not project:
            return Entry(kind="site", key=("site", rel, start, None), name=name, rel=rel)
        entries = {e.key: e for r, s in project if (e := self._declaration_at(rel, r, s)) is not None}
        if len(entries) != 1:
            raise cannot_rename()
        return next(iter(entries.values()))

    def _declaration_at(self, located: str, rel: str, start: int) -> Entry | None:
        """The entry of the declaration at `start` of `rel`; the module itself at its start."""
        module = self.module(rel)
        source = self.snapshot.source(rel)
        if module is None:
            return None
        end = name_end(source.text, start)
        if end > start:
            found = self._binding(rel, module, start, nfkc(source.text[start:end]))
            if found is not None:
                return found
        if start == 0:
            dotted = self.layout.modname(self.root / rel)
            stem = Path(rel).parent.name if Path(rel).stem == "__init__" else Path(rel).stem
            return self._module_entry(located, dotted, stem)
        return None


class Trace(BaseModel):
    """What an occurrence resolves to statically: the import bindings it passes through and the declarations it
    reaches (each declaration's whole group), and whether it reaches any declaration or module at all."""

    model_config = ConfigDict(frozen=True)

    sites: frozenset[Site]
    resolved: bool


class StaticTrace:
    """Traces names, imports and aliases by Python's scoping over the project's own modules."""

    def __init__(self, locator: EntryLocator) -> None:
        self.locator = locator
        self._seen: set[tuple[str, str]] = set()

    def at(self, rel: str, start: int, name: str) -> Trace:
        """The trace of the name, import or alias occurrence of `name` at `start` of `rel`."""
        module = self.locator.module(rel)
        if module is None:
            return Trace(sites=frozenset(), resolved=False)
        source = self.locator.snapshot.source(rel)
        own = next(((scope, node) for scope, bound, node in module.binder.bound
                    if bound == name and bound_at(source, node, bound) == start), None)
        self._seen = set()
        if own is not None:
            return self._binding(rel, module, own[1], name)
        node = source.name_at(start)
        scope = self.locator.load_scopes(rel, module).get(id(node)) if isinstance(node, ast.Name) else None
        if scope is None:
            return Trace(sites=frozenset(), resolved=False)
        return self._scope(rel, module, scope.resolving(name), name)

    def _scope(self, rel: str, module: Module, owner: Scope, name: str) -> Trace:
        nodes = [node for scope, bound, node in module.binder.bound if bound == name and scope.owner(name) is owner]
        traces = [self._binding(rel, module, node, name) for node in nodes]
        if owner.kind == "module":
            traces += [self._module(dotted, name, star=True) for dotted in module.stars]
        return _joined(traces)

    def _binding(self, rel: str, module: Module, node: ast.AST, name: str) -> Trace:
        """A binding of `name`: an import followed through its module; any other declaration, its group."""
        source = self.locator.snapshot.source(rel)
        if not isinstance(node, ast.alias):
            entry = self.locator.group_at(rel, module, node, name)
            return Trace(sites=frozenset(entry.sites if entry is not None else ()), resolved=entry is not None)
        own = bound_at(source, node, name)
        sites = frozenset({(rel, own)} if own is not None else ())
        stmt = source.parent(node)
        if isinstance(stmt, ast.Import):
            dotted = node.name if node.asname else name
            return Trace(sites=sites, resolved=self.locator.folders(dotted) is not None)
        if not isinstance(stmt, ast.ImportFrom) or node.name == "*":
            return Trace(sites=sites, resolved=False)
        found = self._module(module.binder.from_module(stmt), node.name, star=False)
        return Trace(sites=sites | found.sites, resolved=found.resolved)

    def _module(self, dotted: str | None, name: str, *, star: bool) -> Trace:
        """`name` read from module `dotted`: its bindings there, else a submodule of that name."""
        if dotted is None or (dotted, name) in self._seen:
            return Trace(sites=frozenset(), resolved=False)
        self._seen.add((dotted, name))
        loaded = self.locator.resolver.load(dotted)
        at = self.locator.module_at(loaded) if loaded is not None else None
        if at is None:
            return Trace(sites=frozenset(), resolved=False)
        rel, target = at
        if star and (name not in target.all_names if target.all_names is not None else name.startswith("_")):
            return Trace(sites=frozenset(), resolved=False)
        found = self._scope(rel, target, target.scope, name)
        if found.sites or found.resolved or star:
            return found
        return Trace(sites=frozenset(), resolved=self.locator.folders(f"{dotted}.{name}") is not None)


def _joined(traces: list[Trace]) -> Trace:
    return Trace(sites=frozenset().union(*(t.sites for t in traces)), resolved=any(t.resolved for t in traces))


def _module(rel: str, module: str | None, name: str, dotted: str) -> Entry:
    """A module rename located in `rel`: a project module keyed by its file or package directory alone, so every way of
    naming it is one symbol; a library module by its dotted name."""
    key = ("module", module, 0, None) if module is not None else ("module", dotted, 0, dotted)
    return Entry(kind="module", key=key, name=name, rel=rel, module=module)


def _function(rel: str, source: SourceFile, arg: ast.arg) -> Site | None:
    """The def whose signature declares `arg`, by its name; None for a lambda's."""
    up = source.parent(source.parent(arg) or arg)
    span = source.name_span(up) if isinstance(up, _FUNCTIONS) else None
    return (rel, span[0]) if span is not None else None


def _bound_span(source: SourceFile, node: ast.AST, name: str) -> tuple[int, int] | None:
    start = bound_at(source, node, name)
    return (start, start + len(name)) if start is not None else None

