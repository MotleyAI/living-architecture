"""Python dependency edges over repo files (`.py` and `.pyi`): every import, read by `ast` and lexically, resolved by
dotted suffix; and the reverse import closure of a file."""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict

_INITS = ("__init__.py", "__init__.pyi")
_BUILTINS = "__builtins__.pyi"
_STUBS = "-stubs"
_FROM_OR_IMPORT = re.compile(
    r"\bfrom\s+(?P<dots>\.*)\s*(?P<module>[\w.]*)\s+import\s+(?P<names>\([^)]*\)|[^\n;]*)"
    r"|\bimport\s+(?P<plain>[^\n;]*)"
)
_DOTTED = re.compile(r"[^\W\d]\w*(?:\.[^\W\d]\w*)*")


class ImportStmt(BaseModel):
    """`import module` (no names, level 0) or `from <level dots><module> import names` (`star`: `import *`)."""

    model_config = ConfigDict(frozen=True)

    level: int
    module: str
    names: tuple[str, ...] = ()
    star: bool = False


def _tree_imports(tree: ast.AST) -> set[ImportStmt]:
    out: set[ImportStmt] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(ImportStmt(level=0, module=a.name) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names = tuple(a.name for a in node.names if a.name != "*")
            star = any(a.name == "*" for a in node.names)
            out.add(ImportStmt(level=node.level, module=node.module or "", names=names, star=star))
    return out


def _ast_imports(source: bytes) -> set[ImportStmt]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return set()
    return _tree_imports(tree)


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
        out.add(ImportStmt(level=len(m.group("dots")), module=module, names=tuple(_names(names)),
                           star=names.strip().strip("()").strip() == "*"))
    return out


def _module(path: str) -> tuple[str, ...]:
    """The dotted name `path` imports as: a `<name>-stubs` directory as `<name>`, an initializer as its package."""
    parts = PurePosixPath(path).parts
    directory = tuple(p.removesuffix(_STUBS) if p.endswith(_STUBS) else p for p in parts[:-1])
    return directory if parts[-1] in _INITS else (*directory, PurePosixPath(parts[-1]).stem)


class _Graph:
    """Graph files indexed by every dotted suffix of their module name."""

    def __init__(self, paths: list[str]) -> None:
        self.paths = set(paths)
        self.by_suffix: dict[tuple[str, ...], list[str]] = defaultdict(list)
        self.by_dir: dict[tuple[str, ...], set[str]] = defaultdict(set)
        for path in paths:
            module = _module(path)
            for k in range(1, len(module) + 1):
                self.by_suffix[module[-k:]].append(path)
            self.by_dir[PurePosixPath(path).parts[:-1]].add(path)

    def _init(self, directory: tuple[str, ...]) -> set[str]:
        """The package initializers of `directory`, source and stub."""
        return {path for name in _INITS if (path := "/".join((*directory, name))) in self.paths}

    def submodules(self, directory: tuple[str, ...]) -> set[str]:
        """Every module directly in package `directory`: its files, and its subpackages' initializers."""
        out: set[str] = set()
        for path in self.by_dir.get(directory, ()):
            parts = PurePosixPath(path).parts
            if parts[-1] in _INITS:
                continue
            out.add(path)
        for sub in {p[len(directory)] for p in self.by_dir if len(p) > len(directory) and p[: len(directory)] == directory}:
            out |= self._init((*directory, sub))
        return out

    def absolute(self, dotted: str) -> set[str]:
        """Files ending in the dotted path at a directory boundary, with the package initializers along each."""
        want = tuple(dotted.split("."))
        out: set[str] = set()
        for path in self.by_suffix.get(want, []):
            out.add(path)
            parts = PurePosixPath(path).parts
            root = len(parts) - len(want) - (parts[-1] in _INITS)
            for depth in range(1, len(want)):
                out |= self._init(parts[: root + depth])
        return out

    def packages(self, dotted: str) -> set[tuple[str, ...]]:
        """The directories of the packages the dotted path names."""
        return {PurePosixPath(p).parts[:-1] for p in self.by_suffix.get(tuple(dotted.split(".")), [])
                if PurePosixPath(p).name in _INITS}

    def in_dir(self, directory: tuple[str, ...], name: str) -> set[str]:
        """`<directory>/name.py`, `name.pyi` and `name/__init__.py(i)`, where present."""
        candidates = ("/".join((*directory, f"{name}.py")), "/".join((*directory, f"{name}.pyi")))
        return {c for c in candidates if c in self.paths} | self._init((*directory, name))

    def relative(self, importer: str, stmt: ImportStmt) -> set[str]:
        """A relative import's module, each imported name as a module, and the packages along the way."""
        directory = PurePosixPath(importer).parts[:-1]
        if stmt.level - 1 > len(directory):
            return set()
        base = directory[: len(directory) - (stmt.level - 1)]
        out = self._init(base)
        module = tuple(stmt.module.split(".")) if stmt.module else ()
        for i, part in enumerate(module):
            out |= self.in_dir(base + module[:i], part)
        target = base + module
        for name in stmt.names:
            out |= self.in_dir(target, name)
        if stmt.star:
            out |= self.submodules(target)
        return out

    def package_chain(self, path: str) -> set[str]:
        """The `__init__.py` of each directory containing `path`, up to the first directory without one."""
        out: set[str] = set()
        directory = PurePosixPath(path).parts[:-1]
        while True:
            inits = self._init(directory)
            if not inits:
                return out
            out |= inits - {path}
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
    if stmt.star:
        for package in graph.packages(stmt.module):
            out |= graph.submodules(package)
    return out


def dependency_edges(repo_root: Path, *, files: list[str], deleted: list[str]) -> list[tuple[str, str]]:
    """(importer, target) repo-relative pairs over `files` (read when regular; OSError when that fails) and `deleted` (targets only); no self-edges."""
    graph = _Graph([*files, *deleted])
    edges: set[tuple[str, str]] = set()
    for path in files:
        file = repo_root / path
        source = file.read_bytes() if file.is_file() else b""
        targets = graph.package_chain(path)
        for stmt in _ast_imports(source) | _lexical_imports(source):
            targets |= _resolve(graph, path, stmt)
        edges.update((path, target) for target in targets if target != path)
    return sorted(edges)


def reverse_closure(target: str, sources: Mapping[str, ast.AST | str]) -> set[str]:
    """Every file of `sources` whose import statements reach `target`, `target` included; each source is its parsed
    tree, or its text (read lexically) when it does not parse. A `__builtins__.pyi` is imported by every file."""
    graph = _Graph(list(sources))
    builtins = {path for path in sources if PurePosixPath(path).name == _BUILTINS}
    importers: dict[str, set[str]] = defaultdict(set)
    for path, source in sources.items():
        stmts = _tree_imports(source) if isinstance(source, ast.AST) else _lexical_imports(source.encode("utf-8", "replace"))
        targets = {t for stmt in stmts for t in _resolve(graph, path, stmt)} | builtins
        for t in targets - {path}:
            importers[t].add(path)
    out = {target}
    pending = [target]
    while pending:
        for importer in importers.get(pending.pop(), ()):
            if importer not in out:
                out.add(importer)
                pending.append(importer)
    return out
