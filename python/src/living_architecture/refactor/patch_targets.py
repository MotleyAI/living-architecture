"""Dotted `patch` targets resolved statically to project declarations: modules found under the source folders, then
module bindings, then class attributes along the C3 method resolution order."""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

from living_architecture.refactor.members import member_declarations
from living_architecture.refactor.static_resolver import Module, Resolver, Value, node_key


class SourceFolders:
    """The project's modules: `a.b` is `<folder>/a/b.py` or `<folder>/a/b/__init__.py` under each source folder."""

    def __init__(self, folders: list[Path]) -> None:
        self.folders = folders

    def files(self, dotted: str) -> list[tuple[Path, bool]]:
        """Every distinct file of module `dotted`, with whether it is a package's `__init__`."""
        parts = dotted.split(".")
        if not all(p.isidentifier() for p in parts):
            return []
        found: dict[Path, bool] = {}
        for folder in self.folders:
            base = folder.joinpath(*parts)
            for path, is_package in ((base / "__init__.py", True), (base.parent / f"{base.name}.py", False)):
                if path.is_file():
                    found.setdefault(path.resolve(), is_package)
        return list(found.items())

    def __call__(self, dotted: str) -> tuple[Path, bool] | None:
        files = self.files(dotted)
        return files[0] if len(files) == 1 else None

    def top_level(self, name: str) -> bool:
        """`name` is a top-level module, package or namespace directory of some source folder."""
        return bool(self.files(name)) or any((folder / name).is_dir() for folder in self.folders if name.isidentifier())


ClassRef = tuple[Module, ast.ClassDef]
# A segment's declarations, each with its module; an empty list for a module segment.
Resolved = list[list[tuple[Module, ast.AST]]]


class _Opaque:
    """A base class that does not resolve."""


class TargetResolver:
    """Resolves dotted targets; None for a target that does not land on exactly one declaration."""

    def __init__(self, folders: SourceFolders, read: Callable[[Path], str]) -> None:
        self.folders = folders
        self.resolver = Resolver(folders, read)
        self._mros: dict[tuple[str, str], list[ClassRef | _Opaque] | None] = {}
        self._active: set[tuple[str, str]] = set()

    def _class_of(self, value: Value) -> ClassRef | None:
        found = self.resolver.declaration(value)
        return (found[0], found[1]) if found is not None and isinstance(found[1], ast.ClassDef) else None

    def _bases(self, ref: ClassRef) -> list[ClassRef | _Opaque]:
        module, cls = ref
        scope = module.binder.enclosing[node_key(cls)]
        out: list[ClassRef | _Opaque] = []
        for base in cls.bases:
            expr = base.value if isinstance(base, ast.Subscript) else base
            value = self.resolver.resolve(module, scope, expr)
            if value is not None and value[0] == "typing":
                continue
            if value is None and isinstance(expr, ast.Name) and expr.id == "object":
                continue
            found = self._class_of(value)
            out.append(found if found is not None else _Opaque())
        return out

    def mro(self, ref: ClassRef) -> list[ClassRef | _Opaque] | None:
        """C3 linearization; an unresolved base is a leaf; None for a cycle or an inconsistent order."""
        key = (ref[0].dotted, node_key(ref[1]))
        if key in self._mros:
            return self._mros[key]
        if key in self._active:
            return None
        self._active.add(key)
        try:
            bases = self._bases(ref)
            lines = [self.mro(b) if not isinstance(b, _Opaque) else [b] for b in bases]
            known = [line for line in lines if line is not None]
            result = _c3(ref, [*known, bases]) if len(known) == len(lines) else None
        finally:
            self._active.discard(key)
        self._mros[key] = result
        return result

    def attribute(self, ref: ClassRef, name: str) -> list[tuple[Module, ast.AST]] | None:
        """The declarations of `name` in the first class of `ref`'s MRO declaring it; None past an unresolved base."""
        for entry in self.mro(ref) or [_Opaque()]:
            if isinstance(entry, _Opaque):
                return None
            found = member_declarations(entry[1], name)
            if found:
                return [(entry[0], node) for node in found]
        return None

    def resolve(self, target: str) -> Resolved | None:
        """Each segment's declarations, or None when the target does not resolve."""
        segments = target.split(".")
        start = next((i for i in range(len(segments), 0, -1) if self.folders.files(".".join(segments[:i]))), 0)
        if start == 0 or any(len(self.folders.files(".".join(segments[:j]))) > 1 for j in range(1, start + 1)):
            return None
        out: Resolved = [[] for _ in range(start)]
        module: str | None = ".".join(segments[:start])
        cls: ClassRef | None = None
        for name in segments[start:]:
            if module is not None:
                value = self.resolver.member(module, name)
                if value is not None and value[0] == "module":
                    out.append([])
                    module = value[1]
                    continue
                found = self.resolver.declaration(value)
                declared = [found] if found is not None else None
            else:
                declared = self.attribute(cls, name) if cls is not None else None
            if declared is None:
                return None
            out.append(declared)
            module = None
            cls = (declared[0][0], declared[0][1]) if len(declared) == 1 and isinstance(declared[0][1], ast.ClassDef) else None
        return out


def _c3(ref: ClassRef, sequences: list[list[ClassRef | _Opaque]]) -> list[ClassRef | _Opaque] | None:
    def same(a: ClassRef | _Opaque, b: ClassRef | _Opaque) -> bool:
        if isinstance(a, _Opaque) or isinstance(b, _Opaque):
            return a is b
        return a[0].dotted == b[0].dotted and a[1] is b[1]

    result: list[ClassRef | _Opaque] = [ref]
    pending = [list(s) for s in sequences if s]
    while pending:
        head = next(
            (s[0] for s in pending if not any(any(same(s[0], x) for x in other[1:]) for other in pending)), None
        )
        if head is None:
            return None
        result.append(head)
        pending = [[x for x in s if not same(x, head)] for s in pending]
        pending = [s for s in pending if s]
    return result
