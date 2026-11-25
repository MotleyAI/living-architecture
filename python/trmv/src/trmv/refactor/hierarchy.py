"""Python member hierarchies over the checker's class graph: rope's in-hierarchy rule (a class's roots for a member name)
evaluated on the classes basedpyright resolves each base to."""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from trmv.lang import Span
from trmv.refactor.members import member_declarations
from trmv.refactor.python_source import SourceFile

ClassKey = tuple[Path, int]
# A linearized class, or None for a base that resolves to no class.
Linearized = list["GraphClass | None"]


class Definitions(Protocol):
    def definition(self, path: Path, offset: int) -> list[Span]: ...


class GraphClass:
    """A class declaration: its file, node and key (its file and the start of its name)."""

    def __init__(self, source: SourceFile, node: ast.ClassDef) -> None:
        self.source = source
        self.node = node
        name = source.name_span(node)
        self.key: ClassKey = (source.path, name[0] if name else -1)


def _base_name(expr: ast.expr) -> ast.expr | None:
    if isinstance(expr, ast.Subscript):
        expr = expr.value
    return expr if isinstance(expr, (ast.Name, ast.Attribute)) else None


def _merge(cls: GraphClass, orders: list[Linearized]) -> Linearized | None:
    """C3: `cls`, then the head of the first of `orders` that no other order holds past its head, repeatedly."""
    out: Linearized = [cls]
    pending = [list(o) for o in orders if o]
    while pending:
        head = next((o[0] for o in pending if not any(_holds(other[1:], o[0]) for other in pending)), cls)
        if head is cls:
            return None
        out.append(head)
        pending = [rest for o in pending if (rest := o[1:] if _same(o[0], head) else o)]
    return out


def _same(a: GraphClass | None, b: GraphClass | None) -> bool:
    return a is b if a is None or b is None else a.key == b.key


def _holds(order: Linearized, item: GraphClass | None) -> bool:
    return item is not None and any(_same(o, item) for o in order)


class ClassGraph:
    """Classes, their bases as the checker resolves them, and the roots of a member name in each."""

    def __init__(self, definitions: Definitions, load: Callable[[Path], SourceFile | None]) -> None:
        self._definitions = definitions
        self._load = load
        self._classes: dict[ClassKey, GraphClass | None] = {}
        self._bases: dict[ClassKey, list[GraphClass]] = {}
        self._has: dict[tuple[ClassKey, str], bool] = {}
        self._roots: dict[tuple[ClassKey, str], frozenset[ClassKey]] = {}
        self._mro: dict[ClassKey, Linearized | None] = {}

    def at(self, path: Path, start: int) -> GraphClass | None:
        """The class whose name starts at `start` of the file at `path`."""
        key = (path, start)
        if key not in self._classes:
            source = self._load(path)
            self._classes[key] = None
            if source is not None and source.tree is not None:
                for node in source.nodes:
                    if isinstance(node, ast.ClassDef) and (span := source.name_span(node)) is not None and span[0] == start:
                        self._classes[key] = GraphClass(source, node)
                        break
        return self._classes[key]

    def of(self, source: SourceFile, node: ast.ClassDef) -> GraphClass:
        found = GraphClass(source, node)
        return self._classes.setdefault(found.key, found) or found

    def bases(self, cls: GraphClass) -> list[GraphClass]:
        """The classes `cls`'s bases resolve to, in base order; a base resolving to no class is left out."""
        if cls.key not in self._bases:
            out: list[GraphClass] = []
            for base in cls.node.bases:
                for found in self._base_classes(cls.source, base):
                    if all(f.key != found.key for f in out):
                        out.append(found)
            self._bases[cls.key] = out
        return self._bases[cls.key]

    def mro(self, cls: GraphClass, seen: frozenset[ClassKey] = frozenset()) -> Linearized | None:
        """`cls`'s method resolution order, None standing for each base that resolves to no class; None when the
        bases have no consistent order."""
        if cls.key in seen:
            return None
        if cls.key not in self._mro:
            parents: Linearized = []
            for base in cls.node.bases:
                parents += self._base_classes(cls.source, base) or [None]
            tails: list[Linearized | None] = [[None] if p is None else self.mro(p, seen | {cls.key}) for p in parents]
            orders = [t for t in tails if t is not None]
            self._mro[cls.key] = _merge(cls, [*orders, parents]) if len(orders) == len(tails) else None
        return self._mro[cls.key]

    def lookup(self, cls: GraphClass, name: str) -> GraphClass | bool:
        """The first class of `cls`'s resolution order declaring member `name`; False when none does, True when the
        order cannot be followed that far."""
        for found in self.mro(cls) or [None]:
            if found is None:
                return True
            if member_declarations(found.node, name):
                return found
        return False

    def _base_classes(self, source: SourceFile, base: ast.expr) -> list[GraphClass]:
        name = _base_name(base)
        span = source.name_span(name) if name is not None else None
        if span is None:
            return []
        found = (self.at(d.path, d.start) for d in self._definitions.definition(source.path, span[0]))
        return [c for c in found if c is not None]

    def has(self, cls: GraphClass, name: str, seen: frozenset[ClassKey] = frozenset()) -> bool:
        """`cls` declares member `name` or inherits it."""
        key = (cls.key, name)
        if key not in self._has:
            if cls.key in seen:
                return False
            self._has[key] = bool(member_declarations(cls.node, name)) or any(
                self.has(b, name, seen | {cls.key}) for b in self.bases(cls))
        return self._has[key]

    def roots(self, cls: GraphClass, name: str, seen: frozenset[ClassKey] = frozenset()) -> frozenset[ClassKey]:
        """The roots of each base of `cls` that has `name`; `cls` itself when none has."""
        key = (cls.key, name)
        if key not in self._roots:
            if cls.key in seen:
                return frozenset({cls.key})
            found: set[ClassKey] = set()
            for base in self.bases(cls):
                if self.has(base, name):
                    found |= self.roots(base, name, seen | {cls.key})
            self._roots[key] = frozenset(found or {cls.key})
        return self._roots[key]
