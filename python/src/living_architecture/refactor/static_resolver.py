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
_TYPE_ALIAS: type[ast.stmt] | None = getattr(ast, "TypeAlias", None)  # Python 3.12+

ScopeKind = Literal["module", "class", "function", "comprehension", "annotation"]
# ("typing", member) is a member of typing / typing_extensions; ("module", dotted) a module; ("decl", key) a
# declaration of a first-party module (`Resolver.declaration` finds it); None anything else.
Value = tuple[Literal["typing", "module", "decl"], str] | None
# ("module", dotted, "") is `import`, ("member", module, name) `from module import name`, ("decl", module, key) a
# def, class or assigned name; None any other binding.
Binding = tuple[Literal["module", "member", "decl"], str | None, str] | None
ANY: Value = ("typing", "Any")
# A dotted module name to its file and whether it is a package's `__init__`; None when it is not exactly one file.
ModuleFinder = Callable[[str], tuple[Path, bool] | None]


def _field(node: ast.AST, name: str) -> object:
    """A field of `node` that Python 3.11's `ast` may lack (PEP 695), else None."""
    return getattr(node, name, None)


def node_key(node: ast.AST) -> str:
    return f"{getattr(node, 'lineno', 0)}:{getattr(node, 'col_offset', 0)}"


def combine(values: list[Value]) -> Value:
    """The one value every binding agrees on, else None."""
    first = values[0] if values else None
    return first if first is not None and all(v == first for v in values) else None


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
        """The enclosing non-module scopes, innermost first; a class is skipped unless an annotation scope sits in it."""
        scope, sees_class = self.parent, self.kind == "annotation"
        while scope is not None and scope.kind != "module":
            if scope.kind != "class" or sees_class:
                yield scope
            sees_class = sees_class and scope.kind == "annotation"
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
        """Record `node` as a declaration made in `scope`; its binding."""
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

    def _type_params(self, node: ast.AST, scope: Scope) -> Scope:
        """The PEP 695 annotation scope binding `node`'s type parameters, their bounds read in it; else `scope`."""
        params = _field(node, "type_params")
        if not isinstance(params, list) or not params:
            return scope
        inner = self._new("annotation", scope)
        for param in params:
            inner.raw[str(_field(param, "name"))].append(None)
            for expr in (_field(param, "bound"), _field(param, "default_value")):
                parts = expr.elts if isinstance(expr, ast.Tuple) else [expr]
                self.annotations += [(part, inner) for part in parts if isinstance(part, ast.expr)]
        return inner

    def _signature(self, args: ast.arguments, scope: Scope, annotated: Scope) -> list[ast.arg]:
        """`args`' defaults read in `scope`, annotations and type comments in `annotated`; the parameters."""
        params = [*args.posonlyargs, *args.args, args.vararg, *args.kwonlyargs, args.kwarg]
        for default in [*args.defaults, *args.kw_defaults]:
            if default is not None:
                self.visit(default, scope)
        present = [p for p in params if p is not None]
        for param in present:
            if param.annotation is not None:
                self.annotations.append((param.annotation, annotated))
            self._comment(param, param.type_comment, annotated)
        return present

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda, scope: Scope) -> None:
        annotated = scope
        if not isinstance(node, ast.Lambda):
            for decorator in node.decorator_list:
                self.visit(decorator, scope)
            annotated = self._type_params(node, scope)
            if node.returns is not None:
                self.annotations.append((node.returns, annotated))
            self._comment(node, node.type_comment, annotated, signature=True)
            scope.raw[node.name].append(self._decl(node, scope))
        inner = self._new("function", annotated)
        for param in self._signature(node.args, scope, annotated):
            inner.raw[param.arg].append(None)
        for child in node.body if isinstance(node.body, list) else [node.body]:
            self.visit(child, inner)

    def _class(self, node: ast.ClassDef, scope: Scope) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator, scope)
        annotated = self._type_params(node, scope)
        for expr in [*node.bases, *(k.value for k in node.keywords)]:
            self.visit(expr, annotated)
        scope.raw[node.name].append(self._decl(node, annotated))
        inner = self._new("class", annotated)
        for stmt in node.body:
            self.visit(stmt, inner)

    def _type_alias(self, node: ast.stmt, scope: Scope) -> None:
        """A `type` statement: the name binds in `scope`, the value is a type expression in its parameters' scope."""
        if isinstance(name := _field(node, "name"), ast.AST):
            self.visit(name, scope)
        if isinstance(value := _field(node, "value"), ast.expr):
            self.annotations.append((value, self._type_params(node, scope)))

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
        if self._scoped(node, scope) or self._leaf(node, scope):
            return
        self._record(node, scope)
        for child in ast.iter_child_nodes(node):
            self.visit(child, scope)

    def _scoped(self, node: ast.AST, scope: Scope) -> bool:
        """Visits a node that opens a scope or imports; whether it was one."""
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            self._function(node, scope)
        elif isinstance(node, ast.ClassDef):
            self._class(node, scope)
        elif isinstance(node, _COMPREHENSIONS):
            self._comprehension(node, scope)
        elif isinstance(node, ast.Import | ast.ImportFrom):
            self._imports(node, scope)
        elif _TYPE_ALIAS is not None and isinstance(node, _TYPE_ALIAS):
            self._type_alias(node, scope)
        else:
            return False
        return True

    def _leaf(self, node: ast.AST, scope: Scope) -> bool:
        """Visits a name, walrus or annotated assignment; whether it was one."""
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                self.loads.append((node, scope))
            else:
                scope.raw[node.id].append(self._decl(node, scope))
        elif isinstance(node, ast.NamedExpr):
            target = scope
            while target.kind == "comprehension" and target.parent is not None:
                target = target.parent
            target.raw[node.target.id].append(None)
            self.visit(node.value, scope)
        elif isinstance(node, ast.AnnAssign):
            self.annotations.append((node.annotation, scope))
            for part in [node.target, node.value]:
                if part is not None:
                    self.visit(part, scope)
        else:
            return False
        return True

    def _record(self, node: ast.AST, scope: Scope) -> None:
        """Records what any other node declares, binds or loads itself, before its children are visited."""
        if isinstance(node, ast.Global):
            scope.globals.update(node.names)
        elif isinstance(node, ast.Nonlocal):
            scope.nonlocals.update(node.names)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            self.loads.append((node, scope))
        elif isinstance(node, ast.Assign | ast.For | ast.AsyncFor | ast.With | ast.AsyncWith):
            self._comment(node, node.type_comment, scope)
        if (name := self._named_target(node)) is not None:
            scope.raw[name].append(None)


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
        except (OSError, SyntaxError, ValueError):
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
