"""Python dependency edges over repo files: every import, read by `ast` and lexically, resolved by dotted suffix."""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict

_INIT_PY = "__init__.py"
_FROM_OR_IMPORT = re.compile(
    r"\bfrom\s+(?P<dots>\.*)\s*(?P<module>[\w.]*)\s+import\s+(?P<names>\([^)]*\)|[^\n;]*)"
    r"|\bimport\s+(?P<plain>[^\n;]*)"
)
_DOTTED = re.compile(r"[^\W\d]\w*(?:\.[^\W\d]\w*)*")


class ImportStmt(BaseModel):
    """`import module` (no names, level 0) or `from <level dots><module> import names`."""

    model_config = ConfigDict(frozen=True)

    level: int
    module: str
    names: tuple[str, ...] = ()


def _ast_imports(source: bytes) -> set[ImportStmt]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return set()
    out: set[ImportStmt] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(ImportStmt(level=0, module=a.name) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names = tuple(a.name for a in node.names if a.name != "*")
            out.add(ImportStmt(level=node.level, module=node.module or "", names=names))
    return out


def _names(clause: str) -> list[str]:
    """The dotted names of a comma-separated import clause, aliases and comments dropped."""
    out = []
    for item in clause.strip().strip("()").split(","):
        match = _DOTTED.match(item.strip())
        if match:
            out.append(match.group(0))
    return out


def _lexical_imports(source: bytes) -> set[ImportStmt]:
    text = re.sub(r"\\\r?\n", " ", source.decode("utf-8", "replace"))
    out: set[ImportStmt] = set()
    for m in _FROM_OR_IMPORT.finditer(text):
        if m.group("plain") is not None:
            out.update(ImportStmt(level=0, module=name) for name in _names(m.group("plain").split("#", 1)[0]))
            continue
        module = m.group("module")
        if module and not _DOTTED.fullmatch(module):
            continue
        names = "\n".join(line.split("#", 1)[0] for line in m.group("names").splitlines())
        out.add(ImportStmt(level=len(m.group("dots")), module=module, names=tuple(_names(names))))
    return out


class _Graph:
    """Graph files indexed by every dotted suffix of their module name."""

    def __init__(self, paths: list[str]) -> None:
        self.paths = set(paths)
        self.by_suffix: dict[tuple[str, ...], list[str]] = defaultdict(list)
        for path in paths:
            parts = PurePosixPath(path).parts
            module = parts[:-1] if parts[-1] == _INIT_PY else (*parts[:-1], PurePosixPath(parts[-1]).stem)
            for k in range(1, len(module) + 1):
                self.by_suffix[module[-k:]].append(path)

    def _init(self, directory: tuple[str, ...]) -> str | None:
        path = "/".join((*directory, _INIT_PY))
        return path if path in self.paths else None

    def absolute(self, dotted: str) -> set[str]:
        """Files ending in the dotted path at a directory boundary, with the package initializers along each."""
        want = tuple(dotted.split("."))
        out: set[str] = set()
        for path in self.by_suffix.get(want, []):
            out.add(path)
            parts = PurePosixPath(path).parts
            root = len(parts) - len(want) - (parts[-1] == _INIT_PY)
            for depth in range(1, len(want)):
                init = self._init(parts[: root + depth])
                if init is not None:
                    out.add(init)
        return out

    def in_dir(self, directory: tuple[str, ...], name: str) -> set[str]:
        """`<directory>/name.py` and `<directory>/name/__init__.py`, where present."""
        candidates = ("/".join((*directory, f"{name}.py")), "/".join((*directory, name, _INIT_PY)))
        return {c for c in candidates if c in self.paths}

    def relative(self, importer: str, stmt: ImportStmt) -> set[str]:
        """A relative import's module, each imported name as a module, and the packages along the way."""
        directory = PurePosixPath(importer).parts[:-1]
        if stmt.level - 1 > len(directory):
            return set()
        base = directory[: len(directory) - (stmt.level - 1)]
        out = {init for init in [self._init(base)] if init is not None}
        module = tuple(stmt.module.split(".")) if stmt.module else ()
        for i, part in enumerate(module):
            out |= self.in_dir(base + module[:i], part)
        target = base + module
        for name in stmt.names:
            out |= self.in_dir(target, name)
        return out

    def package_chain(self, path: str) -> set[str]:
        """The `__init__.py` of each directory containing `path`, up to the first directory without one."""
        out: set[str] = set()
        directory = PurePosixPath(path).parts[:-1]
        while True:
            init = self._init(directory)
            if init is None:
                return out
            if init != path:
                out.add(init)
            if not directory:
                return out
            directory = directory[:-1]


def _resolve(graph: _Graph, importer: str, stmt: ImportStmt) -> set[str]:
    if stmt.level:
        return graph.relative(importer, stmt)
    if not stmt.module:
        return set()
    out = graph.absolute(stmt.module)
    for name in stmt.names:
        out |= graph.absolute(f"{stmt.module}.{name}")
    return out


def dependency_edges(repo_root: Path, *, files: list[str], deleted: list[str]) -> list[tuple[str, str]]:
    """(importer, target) repo-relative pairs over `files` (read) and `deleted` (targets only); no self-edges."""
    graph = _Graph([*files, *deleted])
    edges: set[tuple[str, str]] = set()
    for path in files:
        try:
            source = (repo_root / path).read_bytes()
        except OSError:
            source = b""
        targets = graph.package_chain(path)
        for stmt in _ast_imports(source) | _lexical_imports(source):
            targets |= _resolve(graph, path, stmt)
        edges.update((path, target) for target in targets if target != path)
    return sorted(edges)
