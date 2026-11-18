"""A word table's carve-outs over Python syntax: the declarations they match (by written annotation, by path, by
symbol), the mentions they cover, and the fixture decorators of the language registry."""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterable
from pathlib import Path

from deterministic_refactor.contract import glob_match, language, message
from deterministic_refactor.refactor.locators import RefactorError, project_rel
from deterministic_refactor.refactor.python_source import SourceFile, every_parameter
from deterministic_refactor.refactor.symbol_path import (
    declared_scopes,
    is_wildcard,
    locate,
    wildcard_refused,
)
from deterministic_refactor.refactor.word_table import WordTable, held_words

_IDENTIFIER = re.compile(r"[^\W\d]\w*")
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
Span = tuple[int, int]


def _annotations(source: SourceFile) -> dict[int, str]:
    """The written annotation of each parameter, variable, field and attribute, by the offset of its name."""
    out: dict[int, str] = {}
    for node in source.nodes:
        named: ast.AST | None = None
        if isinstance(node, ast.arg) and node.annotation is not None:
            named = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, (ast.Name, ast.Attribute)):
            named = node.target
        span = source.name_span(named) if named is not None else None
        if span is not None and isinstance(node, (ast.arg, ast.AnnAssign)) and node.annotation is not None:
            out[span[0]] = source.segment(node.annotation)
    return out


def _imported(source: SourceFile) -> dict[str, str]:
    """The dotted name each import of `source` binds a local name to."""
    out: dict[str, str] = {}
    for node in source.nodes:
        if isinstance(node, ast.Import):
            out.update(_import_binding(alias) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            out.update((alias.asname or alias.name, f"{node.module}.{alias.name}") for alias in node.names)
    return out


def _import_binding(alias: ast.alias) -> tuple[str, str]:
    """`import a.b as c` binds `c` to `a.b`; `import a.b` binds `a` to `a`."""
    if alias.asname:
        return alias.asname, alias.name
    head = alias.name.split(".")[0]
    return head, head


def _dotted(node: ast.expr) -> list[str] | None:
    if isinstance(node, ast.Name):
        return [node.id]
    head = _dotted(node.value) if isinstance(node, ast.Attribute) else None
    return [*head, node.attr] if head is not None and isinstance(node, ast.Attribute) else None


def is_fixture(source: SourceFile, offset: int) -> bool:
    """The function named at `offset` carries a fixture decorator of the registry, bare or called, through the
    file's imports."""
    function = source.defined_at((offset, offset + _name_length(source, offset)))
    if not isinstance(function, _FUNCTIONS):
        return False
    imported = _imported(source)
    fixtures = set(language("python")["fixture_decorators"])
    for decorator in function.decorator_list:
        parts = _dotted(decorator.func if isinstance(decorator, ast.Call) else decorator)
        if parts is not None and ".".join([imported.get(parts[0], parts[0]), *parts[1:]]) in fixtures:
            return True
    return False


def _name_length(source: SourceFile, offset: int) -> int:
    m = _IDENTIFIER.match(source.text, offset)
    return len(m.group()) if m else 0


def _scope_span(source: SourceFile, node: ast.AST) -> Span:
    """A module's whole file; a class's or function's source from its first decorator to its end."""
    if isinstance(node, ast.Module):
        return 0, len(source.text)
    assert isinstance(node, (*_FUNCTIONS, ast.ClassDef))
    start, end = source.span(node)
    if node.decorator_list:
        start = source.text.rfind("@", 0, source.span(node.decorator_list[0])[0])
    return start, end


class CarveOuts:
    """The carve-outs of `table` against the sources of the project at `root` (`source`: a project-relative path's
    file)."""

    def __init__(self, table: WordTable, root: Path, source: Callable[[str], SourceFile]) -> None:
        self.table = table
        self.root = root
        self.source = source
        self._annotations: dict[str, dict[int, str]] = {}
        self._symbols: dict[int, set[tuple[str, int]]] = {}
        self._covered: dict[tuple[str, str], list[Span]] = {}

    def resolve(self) -> None:
        """Locate every `symbols` item; `LocatorError` for a wildcard path or one that names no declaration."""
        for i, carve in enumerate(self.table.carve_outs):
            if carve.matcher != "symbols":
                continue
            sites = self._symbols.setdefault(i, set())
            for item in carve.values:
                file, symbol = str(item["file"]), str(item["symbol"])
                if is_wildcard(symbol):
                    raise wildcard_refused(file, symbol)
                sites.update((rel, offset) for rel in [self._rel(file)] for offset in self._located(rel, symbol, file))

    def _rel(self, file: str) -> str:
        """`file` as a project-relative path; `refactor.outside-project` naming it as written."""
        try:
            return project_rel(self.root, str(self.root / file))
        except RefactorError:
            raise RefactorError(message("refactor.outside-project", path=file)) from None

    def _located(self, rel: str, symbol: str, shown: str) -> tuple[int, ...]:
        try:
            source = self.source(rel)
        except (OSError, UnicodeDecodeError, LookupError):
            source = SourceFile(Path(rel), "")
        return locate(source, symbol, shown).offsets

    def _annotation(self, rel: str, offset: int) -> str | None:
        if rel not in self._annotations:
            self._annotations[rel] = _annotations(self.source(rel))
        return self._annotations[rel].get(offset)

    def _label(self, index: int, rel: str, offsets: Iterable[int], *, module: bool = False) -> str | None:
        """How carve-out `index` matches the declaration at `offsets` of `rel`: its key and the value that matched."""
        carve = self.table.carve_outs[index]
        if carve.matcher == "paths":
            glob = next((g for g in carve.values if glob_match(g, rel)), None)
            return f"paths {glob}" if glob is not None else None
        if module:
            return None
        if carve.matcher == "symbols":
            return "symbols" if any((rel, o) in self._symbols.get(index, ()) for o in offsets) else None
        tokens = {t for o in offsets if (text := self._annotation(rel, o)) is not None for t in _IDENTIFIER.findall(text)}
        name = next((n for n in carve.values if n in tokens), None)
        return f"annotated {name}" if name is not None else None

    def carved(self, rel: str, name: str, offsets: Iterable[int], *, module: bool = False) -> list[tuple[str, str]]:
        """Each word `name` holds that a carve-out keeps for the declaration at `offsets` of `rel` (a `module`: the
        file itself), with the first matching carve-out's label."""
        out: list[tuple[str, str]] = []
        sites = list(offsets)
        for word in held_words(name, self.table.words):
            for index, carve in enumerate(self.table.carve_outs):
                label = self._label(index, rel, sites, module=module) if word in carve.words else None
                if label is not None:
                    out.append((word, label))
                    break
        return out

    def covers(self, rel: str, old: str, offset: int) -> bool:
        """A carve-out for a word `old` holds covers a mention at `offset` of `rel`: by the file's path, or by a
        matched declaration named `old` whose scope holds it."""
        key = (rel, old)
        if key not in self._covered:
            self._covered[key] = self._covering(rel, old)
        return any(start <= offset < end for start, end in self._covered[key])

    def _covering(self, rel: str, old: str) -> list[Span]:
        source = self.source(rel)
        words = set(held_words(old, self.table.words))
        carves = [(i, c) for i, c in enumerate(self.table.carve_outs) if c.words & words]
        if any(c.matcher == "paths" and self._label(i, rel, ()) for i, c in carves):
            return [(0, len(source.text))]
        out: list[Span] = []
        for scope, offsets in _named(source, old):
            if any(c.matcher != "paths" and self._label(i, rel, offsets) for i, c in carves):
                out.append(_scope_span(source, scope))
        return out


def _named(source: SourceFile, name: str) -> list[tuple[ast.AST, list[int]]]:
    """Each scope of `source` declaring `name` (a function its parameter too), with the offsets of the declarations."""
    out: list[tuple[ast.AST, list[int]]] = []
    for scope, declarations in declared_scopes(source):
        offsets = [offset for declared, offset, _ in declarations if declared == name]
        if isinstance(scope, _FUNCTIONS):
            spans = [source.name_span(a) for a in every_parameter(scope.args) if a.arg == name]
            offsets += [span[0] for span in spans if span is not None]
        if offsets:
            out.append((scope, offsets))
    return out

