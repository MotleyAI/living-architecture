"""The literal sources of a name: the plain string literals a once-bound name, constant or loop target holds, followed
through assignments, imports and re-exports of the modules the resolver finds, without running any of them."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from living_architecture.refactor.static_resolver import Module, Resolver, Scope

_DISPLAYS = (ast.Tuple, ast.List, ast.Set)
_MUTATORS = frozenset({
    "add", "append", "clear", "difference_update", "discard", "extend", "insert", "intersection_update", "pop", "remove",
    "reverse", "sort", "symmetric_difference_update", "update",
})


_Key = tuple[int, int, str | int]


def _key(module: Module, scope: Scope, expr: ast.expr) -> _Key:
    return id(module), id(scope), expr.id if isinstance(expr, ast.Name) else id(expr)


def _target(holder: ast.AST | None, expr: ast.expr) -> ast.expr | None:
    """The target `holder` carries the value or the elements of `expr` to."""
    if isinstance(holder, ast.Assign):
        return holder.targets[0] if holder.value is expr and len(holder.targets) == 1 else None
    if isinstance(holder, ast.AnnAssign):
        return holder.target if holder.value is expr else None
    if isinstance(holder, ast.For | ast.AsyncFor | ast.comprehension):
        return holder.target if holder.iter is expr else None
    return None


class Source(BaseModel):
    """A plain string literal: its file, 1-based line, character column and value."""

    model_config = ConfigDict(frozen=True)

    path: Path
    line: int
    col: int
    value: str


class _Step(BaseModel):
    """What a name is bound to: a `value` expression, the iterable of the `loop` binding it, or another `name`."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    kind: Literal["value", "loop", "name"]
    module: Module
    scope: Scope
    expr: ast.expr


class _Facts:
    """One module's parents, bindings and loads by name, and its lines."""

    def __init__(self, module: Module, text: str) -> None:
        self.parents = {id(child): node for node in ast.walk(module.tree) for child in ast.iter_child_nodes(node)}
        self.bound: dict[str, list[tuple[Scope, ast.AST]]] = {}
        for scope, name, node in module.binder.bound:
            self.bound.setdefault(name, []).append((scope, node))
        self.loads: dict[str, list[tuple[ast.Name, Scope]]] = {}
        for expr, scope in module.binder.loads:
            if isinstance(expr, ast.Name):
                self.loads.setdefault(expr.id, []).append((expr, scope))
        self.lines = text.encode().splitlines(keepends=True)

    def literal(self, node: ast.expr) -> tuple[int, str] | None:
        """The character column and value of a quoted string literal on one line, without prefix or escapes."""
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)) or node.lineno != node.end_lineno:
            return None
        if node.lineno > len(self.lines) or node.end_col_offset is None:
            return None
        line = self.lines[node.lineno - 1]
        raw = line[node.col_offset : node.end_col_offset].decode(errors="replace")
        if len(raw) < 2 or raw[0] not in "'\"" or raw[-1] != raw[0] or raw[1:-1] != node.value or raw[0] in node.value:
            return None
        return len(line[: node.col_offset].decode(errors="replace")), node.value

    def sole(self, name: str, node: ast.AST) -> Scope | None:
        """The scope `node` binds `name` in, when it is the name's one binding there and no `global` or `nonlocal`
        statement redirects it."""
        written = next((s for s, n in self.bound.get(name, []) if n is node), None)
        if written is None or written.owner(name) is not written:
            return None
        same = [n for s, n in self.bound[name] if s.owner(name) is written]
        return written if len(same) == 1 else None


class Follower:
    """Follows names to their literal sources over the modules of one resolver."""

    def __init__(self, resolver: Resolver) -> None:
        self.resolver = resolver
        self._facts: dict[int, _Facts | None] = {}
        self._carried: dict[int, set[int]] = {}

    def _of(self, module: Module) -> _Facts | None:
        if id(module) not in self._facts:
            try:
                text = self.resolver.read(module.path) if module.path is not None else None
            except (OSError, ValueError, LookupError):
                text = None
            self._facts[id(module)] = _Facts(module, text) if text is not None else None
        return self._facts[id(module)]

    def _imported(self, module: Module, facts: _Facts, node: ast.alias) -> _Step | None:
        """The name the `from` import `node` binds, in the module it comes from."""
        holder = facts.parents.get(id(node))
        origin = module.binder.from_module(holder) if isinstance(holder, ast.ImportFrom) else None
        target = self.resolver.load(origin) if origin is not None else None
        if target is None:
            return None
        return _Step(kind="name", module=target, scope=target.scope, expr=ast.Name(id=node.name, ctx=ast.Load()))

    def _bound(self, module: Module, facts: _Facts, node: ast.AST, scope: Scope) -> _Step | None:
        """What the sole binding `node` of a name, written in `scope`, binds it to."""
        if isinstance(node, ast.alias):
            return self._imported(module, facts, node)
        holder = facts.parents.get(id(node))
        if not isinstance(node, ast.Name):
            return None
        if isinstance(holder, ast.Assign) and len(holder.targets) == 1 and holder.targets[0] is node:
            return _Step(kind="value", module=module, scope=scope, expr=holder.value)
        if isinstance(holder, ast.AnnAssign) and holder.target is node and holder.value is not None:
            return _Step(kind="value", module=module, scope=scope, expr=holder.value)
        if isinstance(holder, ast.For | ast.AsyncFor) and holder.target is node:
            return _Step(kind="loop", module=module, scope=scope, expr=holder.iter)
        if isinstance(holder, ast.comprehension) and holder.target is node:
            return _Step(kind="loop", module=module, scope=self._iter_scope(facts, holder, scope), expr=holder.iter)
        return None

    @staticmethod
    def _iter_scope(facts: _Facts, generator: ast.comprehension, inner: Scope) -> Scope:
        """The scope a generator's iterable is read in: the enclosing one for a comprehension's first generator."""
        owner = facts.parents.get(id(generator))
        first = isinstance(owner, ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp) and owner.generators[0] is generator
        return inner.parent if first and inner.parent is not None else inner

    def _named(self, module: Module, scope: Scope, name: str) -> _Step | None:
        facts = self._of(module)
        if facts is None:
            return None
        owner = scope.resolving(name)
        found = [(s, n) for s, n in facts.bound.get(name, []) if s.owner(name) is owner]
        if len(found) != 1 or facts.sole(name, found[0][1]) is None:
            return None
        return self._bound(module, facts, found[0][1], found[0][0])

    def _step(self, module: Module, scope: Scope, expr: ast.expr) -> _Step | None:
        """What the name `expr`, or the class constant `K.NAME`, is bound to."""
        if isinstance(expr, ast.Name):
            return self._named(module, scope, expr.id)
        if not isinstance(expr, ast.Attribute):
            return None
        found = self.resolver.declaration(self.resolver.resolve(module, scope, expr.value))
        if found is None or not isinstance(found[1], ast.ClassDef):
            return None
        home, cls = found
        body = home.binder.inner.get(id(cls))
        return self._named(home, body, expr.attr) if body is not None and expr.attr in body.raw else None

    def sources(self, module: Module, scope: Scope, expr: ast.expr, _seen: frozenset[_Key] = frozenset()) -> list[Source]:
        """The literals the string `expr` read in `scope` of `module` holds; none when it is bound any unsupported way."""
        facts = self._of(module)
        if facts is None or module.path is None:
            return []
        if (found := facts.literal(expr)) is not None:
            return [Source(path=module.path, line=expr.lineno, col=found[0], value=found[1])]
        if not isinstance(expr, ast.Name | ast.Attribute):
            return []
        key = _key(module, scope, expr)
        step = self._step(module, scope, expr) if key not in _seen else None
        if step is None:
            return []
        follow = self.elements if step.kind == "loop" else self.sources
        return follow(step.module, step.scope, step.expr, _seen | {key})

    def elements(self, module: Module, scope: Scope, expr: ast.expr, _seen: frozenset[_Key] = frozenset()) -> list[Source]:
        """The literals of the display of plain string literals `expr` is, or that the unmutated once-bound name
        `expr` holds."""
        if isinstance(expr, _DISPLAYS):
            found = [s for elt in expr.elts for s in self.sources(module, scope, elt) if isinstance(elt, ast.Constant)]
            return found if len(found) == len(expr.elts) else []
        key = _key(module, scope, expr)
        if not isinstance(expr, ast.Name) or key in _seen or self._mutated(module, scope, expr.id):
            return []
        step = self._step(module, scope, expr)
        if step is None or step.kind == "loop":
            return []
        return self.elements(step.module, step.scope, step.expr, _seen | {key})

    def _mutated(self, module: Module, scope: Scope, name: str) -> bool:
        """A statement of `module` calls a mutating method on `name`, or assigns or deletes an item of it."""
        facts = self._of(module)
        if facts is None:
            return True
        owner = scope.resolving(name)
        for node, read_in in facts.loads.get(name, []):
            if read_in.resolving(name) is not owner:
                continue
            parent = facts.parents.get(id(node))
            if isinstance(parent, ast.Subscript) and parent.value is node and isinstance(parent.ctx, ast.Store | ast.Del):
                return True
            call = facts.parents.get(id(parent)) if isinstance(parent, ast.Attribute) and parent.attr in _MUTATORS else None
            if isinstance(call, ast.Call) and call.func is parent:
                return True
        return False

    def carried(self, module: Module) -> set[int]:
        """The ids of the loads whose value an assignment or loop carries to a followed name."""
        if id(module) not in self._carried:
            facts = self._of(module)
            self._carried[id(module)] = set() if facts is None else {
                id(expr) for expr, _ in module.binder.loads
                if isinstance(target := _target(facts.parents.get(id(expr)), expr), ast.Name)
                and facts.sole(target.id, target) is not None
            }
        return self._carried[id(module)]


def literal_sources(resolver: Resolver, module: Module, scope: Scope, expr: ast.expr) -> list[Source]:
    """The literal sources of `expr`, a name or `K.NAME` read in `scope` of `module`."""
    return Follower(resolver).sources(module, scope, expr)
