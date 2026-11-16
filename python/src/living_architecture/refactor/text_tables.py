"""Per-run tables the text-only rules read: each file's declared names, exact string literals and comment and string
regions, and the project's prose files, each built once per run so that an entry's cost is a lookup."""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

from living_architecture.config import source_files
from living_architecture.contract import manifest
from living_architecture.refactor.compound import is_compound, words
from living_architecture.refactor.mentions import Region, source_regions
from living_architecture.refactor.outcomes import literal_spans
from living_architecture.refactor.python_source import SourceFile

Span = tuple[int, int]


def declared_name(node: ast.AST) -> str | None:
    """The name a def, class, parameter or assignment target declares."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.arg):
        return node.arg
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        return node.id
    if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
        return node.attr
    return None


class TextTables:
    """The tables of the project at `root`, over `source` (one snapshot)."""

    def __init__(self, root: Path, source: Callable[[str], SourceFile]) -> None:
        self.root = root
        self._source = source
        self._literals: dict[str, dict[str, list[Span]]] = {}
        self._regions: dict[str, list[Region]] = {}
        self._words: dict[str, list[tuple[str, str, Span]]] | None = None
        self._prose: list[str] | None = None

    def literals(self, rel: str) -> dict[str, list[Span]]:
        """The spans of each string literal of `rel` by its value, docstrings and f-string parts aside."""
        if rel not in self._literals:
            self._literals[rel] = literal_spans(self._source(rel))
        return self._literals[rel]

    def regions(self, rel: str) -> list[Region]:
        """The comments and string literal contents of `rel`."""
        if rel not in self._regions:
            self._regions[rel] = list(source_regions(self._source(rel)))
        return self._regions[rel]

    def _declarations(self, rels: list[str]) -> dict[str, list[tuple[str, str, Span]]]:
        if self._words is None:
            self._words = {}
            for rel in rels:
                try:
                    source = self._source(rel)
                except (OSError, UnicodeDecodeError, LookupError):
                    continue
                for node in source.nodes:
                    name = declared_name(node)
                    span = source.name_span(node) if name is not None else None
                    if name is not None and span is not None:
                        for word in {w.lower() for w in words(name)}:
                            self._words.setdefault(word, []).append((rel, name, span))
        return self._words

    def compounds(self, rels: list[str], old: str) -> list[tuple[str, str, Span]]:
        """Each declaration among the files `rels` whose name holds `old` as a word sequence: its file, name, span."""
        wanted = [w.lower() for w in words(old)]
        if not wanted:
            return []
        table = self._declarations(rels)
        first = wanted[0] if len(wanted) > 1 else None
        keys = [first] if first is not None else [wanted[0], f"{wanted[0]}s", f"{wanted[0]}es"]
        found = {entry for key in keys for entry in table.get(key, [])}
        return sorted(entry for entry in found if is_compound(entry[1], old))

    def prose(self) -> list[str]:
        """The project's prose files, by path."""
        if self._prose is None:
            extensions = tuple(manifest()["dr-refactor"]["prose_extensions"])
            self._prose = [rel for rel in sorted(source_files(self.root, [])) if rel.endswith(extensions)]
        return self._prose
