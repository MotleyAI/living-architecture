"""Static name resolution over first-party Python modules: scopes, bindings, imports and re-exports, without
importing or running any of them."""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Literal

TYPING_MODULES = frozenset({"typing", "typing_extensions"})
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)

ScopeKind = Literal["module", "class", "function", "comprehension"]
# ("typing", member) is a member of typing / typing_extensions; ("module", dotted) a module; ("decl", key) a
# declaration of a first-party module (`Resolver.declaration` finds it); None anything else.
Value = tuple[Literal["typing", "module", "decl"], str] | None
# ("module", dotted, "") is `import`, ("member", module, name) `from module import name`, ("decl", module, key) a
# def, class or assigned name; None any other binding.
Binding = tuple[Literal["module", "member", "decl"], str | None, str] | None
ANY: Value = ("typing", "Any")
# A dotted module name to its file and whether it is a package's `__init__`; None when it is not exactly one file.
ModuleFinder = Callable[[str], tuple[Path, bool] | None]


def combine(values: list[Value]) -> Value:
    """The one value every binding agrees on, else None."""
    first = values[0] if values else None
    return first if first is not None and all(v == first for v in values) else None


def node_key(node: ast.AST) -> str:
    return f"{getattr(node, 'lineno', 0)}:{getattr(node, 'col_offset', 0)}"


class Scope:
    def __init__(self, kind: ScopeKind, parent: Scope | None) -> None:
        self.kind: ScopeKind = kind
        self.parent = parent
        self.module: Scope = parent.module if parent is not None else self
        self.raw: defaultdict[str, list[Binding]] = defaultdict(list)
        self.bindings: defaultdict[str, list[Binding]] = defaultdict(list)
        self.globals: set[str] = set()
        self.nonlocals: set[str] = set()

    def _enclosing(self) -> Iterator[Scope]:
        """The enclosing function scopes, innermost first; class scopes are skipped."""
        scope = self.parent
        while scope is not None and scope.kind != "module":
            if scope.kind != "class":
                yield scope
            scope = scope.parent

    def owner(self, name: str) -> Scope:
        """The scope a binding of `name` here binds in."""
        if name in self.globals:
            return self.module
        if name in self.nonlocals:
            for scope in self._enclosing():
                if name in scope.raw or name in scope.nonlocals:
                    return scope.owner(name)
            return self.module
        return self

    def resolving(self, name: str) -> Scope:
        """The scope that resolves a use of `name` here."""
        if name in self.globals or name in self.nonlocals:
            return self.owner(name)
        if self.kind == "module" or name in self.bindings:
            return self
        for scope in self._enclosing():
            if name in scope.globals or name in scope.nonlocals:
                return scope.owner(name)
            if name in scope.bindings:
                return scope
        return self.module


class CommentRoot:
    """A type comment: its node, text, scope and whether it is a function signature's."""

    def __init__(self, node: ast.AST, text: str, scope: Scope, signature: bool) -> None:
        self.node, self.text, self.scope, self.signature = node, text, scope, signature
        self.position: tuple[int, int] = (getattr(node, "lineno", 0), getattr(node, "col_offset", 0))


class Binder:
    """Scopes and bindings of a module, its name and attribute loads, and its type expressions for later reading."""

    def __init__(self, parts: list[str], is_package: bool) -> None:
        self.parts, self.is_package = parts, is_package
        self.dotted = ".".join(parts)
        self.module = Scope("module", None)
        self.scopes = [self.module]
        self.stars: list[str | None] = []
        self.loads: list[tuple[ast.expr, Scope]] = []
        self.annotations: list[tuple[ast.expr, Scope]] = []
        self.comments: list[CommentRoot] = []
        self.decls: dict[str, ast.AST] = {}
        self.enclosing: dict[str, Scope] = {}

    def _new(self, kind: ScopeKind, parent: Scope) -> Scope:
        scope = Scope(kind, parent)
        self.scopes.append(scope)
        return scope

    def _decl(self, node: ast.AST, scope: Scope) -> Binding:
        key = node_key(node)
        self.decls[key] = node
        self.enclosing[key] = scope
        return ("decl", self.dotted, key)

    def _from_module(self, node: ast.ImportFrom) -> str | None:
        if node.level == 0:
            return node.module
        package = self.parts if self.is_package else self.parts[:-1]
        if node.level - 1 >= len(package):
            return None
        return ".".join(package[: len(package) - node.level + 1] + ([node.module] if node.module else []))

    def _comment(self, node: ast.AST, text: str | None, scope: Scope, signature: bool = False) -> None:
        if text is not None:
            self.comments.append(CommentRoot(node, text, scope, signature))

    def _signature(self, args: ast.arguments, scope: Scope) -> list[ast.arg]:
        """`args`' defaults, annotations and type comments read in `scope`; the parameters."""
        params = [*args.posonlyargs, *args.args, args.vararg, *args.kwonlyargs, args.kwarg]
        for default in [*args.defaults, *args.kw_defaults]:
            if default is not None:
                self.visit(default, scope)
        present = [p for p in params if p is not None]
        for param in present:
            if param.annotation is not None:
                self.annotations.append((param.annotation, scope))
            self._comment(param, param.type_comment, scope)
        return present

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda, scope: Scope) -> None:
        if not isinstance(node, ast.Lambda):
            for decorator in node.decorator_list:
                self.visit(decorator, scope)
            if node.returns is not None:
                self.annotations.append((node.returns, scope))
            self._comment(node, node.type_comment, scope, signature=True)
            scope.raw[node.name].append(self._decl(node, scope))
        inner = self._new("function", scope)
        for param in self._signature(node.args, scope):
            inner.raw[param.arg].append(None)
        for child in node.body if isinstance(node.body, list) else [node.body]:
            self.visit(child, inner)

    def _class(self, node: ast.ClassDef, scope: Scope) -> None:
        for expr in [*node.decorator_list, *node.bases, *(k.value for k in node.keywords)]:
            self.visit(expr, scope)
        scope.raw[node.name].append(self._decl(node, scope))
        inner = self._new("class", scope)
        for stmt in node.body:
            self.visit(stmt, inner)

    def _comprehension(self, node: ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp, scope: Scope) -> None:
        self.visit(node.generators[0].iter, scope)
        inner = self._new("comprehension", scope)
        for i, generator in enumerate(node.generators):
            if i:
                self.visit(generator.iter, inner)
            self.visit(generator.target, inner)
            for condition in generator.ifs:
                self.visit(condition, inner)
        for part in [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]:
            self.visit(part, inner)

    def _imports(self, node: ast.Import | ast.ImportFrom, scope: Scope) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                scope.raw[name].append(("module", alias.name if alias.asname else name, ""))
            return
        module = self._from_module(node)
        for alias in node.names:
            if alias.name == "*":
                self.stars.append(module)
            else:
                scope.raw[alias.asname or alias.name].append(("member", module, alias.name))

    @staticmethod
    def _named_target(node: ast.AST) -> str | None:
        """The name an except handler or match pattern binds."""
        if isinstance(node, ast.ExceptHandler | ast.MatchAs | ast.MatchStar):
            return node.name
        if isinstance(node, ast.MatchMapping):
            return node.rest
        return None

    def visit(self, node: ast.AST, scope: Scope) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            return self._function(node, scope)
        if isinstance(node, ast.ClassDef):
            return self._class(node, scope)
        if isinstance(node, _COMPREHENSIONS):
            return self._comprehension(node, scope)
        if isinstance(node, ast.Import | ast.ImportFrom):
            return self._imports(node, scope)
        if isinstance(node, ast.Global):
            scope.globals.update(node.names)
        elif isinstance(node, ast.Nonlocal):
            scope.nonlocals.update(node.names)
        elif isinstance(node, ast.NamedExpr):
            target = scope
            while target.kind == "comprehension" and target.parent is not None:
                target = target.parent
            target.raw[node.target.id].append(None)
            return self.visit(node.value, scope)
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                self.loads.append((node, scope))
            else:
                scope.raw[node.id].append(self._decl(node, scope))
            return None
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            self.loads.append((node, scope))
        elif isinstance(node, ast.AnnAssign):
            self.annotations.append((node.annotation, scope))
            for part in [node.target, node.value]:
                if part is not None:
                    self.visit(part, scope)
            return None
        elif isinstance(node, ast.Assign | ast.For | ast.AsyncFor | ast.With | ast.AsyncWith):
            self._comment(node, node.type_comment, scope)
        if (name := self._named_target(node)) is not None:
            scope.raw[name].append(None)
        for child in ast.iter_child_nodes(node):
            self.visit(child, scope)
        return None


def literal_all(tree: ast.Module) -> set[str] | None:
    """The names of the module's last top-level `__all__` assignment when it is a literal of strings."""
    names: set[str] | None = None
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            targets, value = stmt.targets, stmt.value
        elif isinstance(stmt, ast.AnnAssign):
            targets, value = [stmt.target], stmt.value
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
            continue
        elts = value.elts if isinstance(value, ast.List | ast.Tuple) else None
        strings = [e.value for e in elts or [] if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        names = set(strings) if elts is not None and len(strings) == len(elts) else None
    return names


class Module:
    """A parsed module: its scopes, bindings, star imports and literal `__all__`."""

    def __init__(self, tree: ast.Module, parts: list[str], is_package: bool, path: Path | None = None) -> None:
        self.dotted = ".".join(parts)
        self.path = path
        binder = Binder(parts, is_package)
        for stmt in tree.body:
            binder.visit(stmt, binder.module)
        for scope in binder.scopes:
            for name, found in scope.raw.items():
                scope.owner(name).bindings[name].extend(found)
        self.binder = binder
        self.scope = binder.module
        self.stars = binder.stars
        self.all_names = literal_all(tree)


class Resolver:
    """Resolves names and attributes to values, following the first-party modules `finder` locates."""

    def __init__(self, finder: ModuleFinder, read: Callable[[Path], str] | None = None) -> None:
        self.finder = finder
        self.read = read or (lambda path: path.read_text(encoding="utf-8"))
        self.modules: dict[str, Module | None] = {}
        self.active: set[tuple[str, str]] = set()
        self.cache: dict[tuple[str, str], list[Value]] = {}

    def load(self, dotted: str) -> Module | None:
        if dotted not in self.modules:
            self.modules[dotted] = self._parse(dotted)
        return self.modules[dotted]

    def _parse(self, dotted: str) -> Module | None:
        parts = dotted.split(".")
        if not all(p.isidentifier() for p in parts) or (found := self.finder(dotted)) is None:
            return None
        path, is_package = found
        try:
            return Module(ast.parse(self.read(path)), parts, is_package, path)
        except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
            return None

    def declaration(self, value: Value) -> tuple[Module, ast.AST] | None:
        """The module and node of a `decl` value."""
        if value is None or value[0] != "decl":
            return None
        dotted, _, key = value[1].rpartition("@")
        module = self.modules.get(dotted)
        node = module.binder.decls.get(key) if module is not None else None
        return (module, node) if module is not None and node is not None else None

    def module_values(self, module: Module, name: str) -> list[Value]:
        """The values of every module-level binding of `name`, star imports included."""
        key = (module.dotted, name)
        if key in self.cache:
            return self.cache[key]
        if key in self.active:
            return [None]
        top = not self.active
        self.active.add(key)
        try:
            values = [self.binding_value(b) for b in module.scope.bindings.get(name, [])]
            for star in module.stars:
                values += self.star_values(star, name)
        finally:
            self.active.discard(key)
        if top:
            self.cache[key] = values
        return values

    def binding_value(self, binding: Binding) -> Value:
        if binding is None:
            return None
        kind, module, name = binding
        if kind == "module":
            return ("module", module) if module is not None else None
        if kind == "decl":
            return ("decl", f"{module}@{name}")
        return self.member(module, name)

    def member(self, module: str | None, name: str) -> Value:
        """The value of `module.name`."""
        if module is None:
            return None
        if module in TYPING_MODULES:
            return ("typing", name)
        if (target := self.load(module)) is None:
            return None
        if values := self.module_values(target, name):
            return combine(values)
        return ("module", f"{module}.{name}") if self.load(f"{module}.{name}") is not None else None

    def star_values(self, module: str | None, name: str) -> list[Value]:
        """What `from module import *` binds `name` to, if anything."""
        if module in TYPING_MODULES:
            return [ANY] if name == "Any" else []
        if module is None or (target := self.load(module)) is None:
            return []
        exported = name in target.all_names if target.all_names is not None else not name.startswith("_")
        return self.module_values(target, name) if exported else []

    def values(self, module: Module, scope: Scope, expr: ast.expr) -> list[Value]:
        """The values every binding behind `expr` gives it."""
        if isinstance(expr, ast.Name):
            owner = scope.resolving(expr.id)
            if owner.kind == "module":
                return self.module_values(module, expr.id)
            return [self.binding_value(b) for b in owner.bindings.get(expr.id, [])]
        if isinstance(expr, ast.Attribute):
            return [
                self.member(v[1], expr.attr) if v is not None and v[0] == "module" else None
                for v in self.values(module, scope, expr.value)
            ]
        return [None]

    def resolve(self, module: Module, scope: Scope, expr: ast.expr) -> Value:
        return combine(self.values(module, scope, expr))
