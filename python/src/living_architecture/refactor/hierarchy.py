"""Python member hierarchies over the checker's class graph: rope's in-hierarchy rule (a class's roots for a member name)
evaluated on the classes basedpyright resolves each base to."""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from living_architecture.lang import Span
from living_architecture.refactor.members import member_declarations
from living_architecture.refactor.python_source import SourceFile

ClassKey = tuple[Path, int]


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


class ClassGraph:
    """Classes, their bases as the checker resolves them, and the roots of a member name in each."""

    def __init__(self, definitions: Definitions, load: Callable[[Path], SourceFile | None]) -> None:
        self._definitions = definitions
        self._load = load
        self._classes: dict[ClassKey, GraphClass | None] = {}
        self._bases: dict[ClassKey, list[GraphClass]] = {}
        self._has: dict[tuple[ClassKey, str], bool] = {}
        self._roots: dict[tuple[ClassKey, str], frozenset[ClassKey]] = {}

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
