"""`dr-refactor generate-map`: the rename map of a word table, from syntax alone: one entry per declaration and module
whose name holds a word, the table's entries first, what a carve-out keeps left out and listed."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from living_architecture.contract import YAMLError, language_ids, language_of, load_yaml, message
from living_architecture.refactor.bindings import bound_at
from living_architecture.refactor.carve_outs import CarveOuts
from living_architecture.refactor.entry_location import EntryLocator
from living_architecture.refactor.literal_rename import literal_member_at
from living_architecture.refactor.locators import Locator, RefactorError, project_rel, resolve
from living_architecture.refactor.map_file import MapError
from living_architecture.refactor.python_source import SourceFile
from living_architecture.refactor.rename_union import Session
from living_architecture.refactor.symbol_path import LOCALS, WILDCARD, declared_paths, is_wildcard, locate_all
from living_architecture.refactor.word_table import WordTable, held_words, load_table, replace_words

_PLAIN = re.compile(r"[A-Za-z0-9_$./<>()-]+")
_LOCAL = re.compile(rf"(?:.*\.)?{re.escape(LOCALS)}\.([^.()\[\]]+)")
_INIT = "__init__"
Key = tuple[object, ...]


class Candidate(BaseModel):
    """A declaration (or a module, `offset` None) whose name holds a word: its file, name, canonical key, the offsets
    of its declarations, and the path that locates exactly it."""

    model_config = ConfigDict(frozen=True)

    rel: str
    name: str
    key: Key
    offset: int | None = None
    offsets: tuple[int, ...] = ()
    path: str | None = None


def _scalar(value: object) -> str:
    """A YAML flow scalar: plain unless YAML would read it as something else or it holds any other character."""
    text = str(value)
    if isinstance(value, int):
        return text
    try:
        plain = _PLAIN.fullmatch(text) is not None and load_yaml(text) == text
    except YAMLError:
        plain = False
    return text if plain else "'" + text.replace("'", "''") + "'"


def _line(item: dict[str, Any]) -> str:
    """A map entry as one flow mapping, its keys in schema order."""
    keys = [k for k in ("module", "file", "symbol", "line", "col", "offset", "new_name", "retarget") if k in item]
    return "- {" + ", ".join(f"{k}: {_scalar(item[k])}" for k in keys) + "}"


def _plain_import(node: ast.AST) -> bool:
    """An import binding without an `as` name."""
    return isinstance(node, ast.alias) and node.asname is None


def _entry(source: SourceFile, c: Candidate, new: str) -> dict[str, Any]:
    """A declaration's entry: by its path, else by line and column."""
    if c.path is not None:
        return {"file": c.rel, "symbol": c.path, "new_name": new}
    assert c.offset is not None
    line = source.line(c.offset)
    return {"file": c.rel, "line": line, "col": c.offset - source.line_start(line) + 1, "new_name": new}


def _no_definitions(_rel: str, _offset: int) -> list[tuple[Path, int]]:
    return []


class Generator:
    """The map of `table` over the Python sources of the project at `root`."""

    def __init__(self, root: Path, table: WordTable) -> None:
        self.table = table
        self.session = Session(root)
        self.root = self.session.root
        self.locator = EntryLocator(self.root, _no_definitions, self.session.snapshot, self.session.layout)
        self.carves = CarveOuts(table, self.root, self.session.snapshot.source)
        self.listed: list[tuple[str, int, int, str]] = []

    # ---- the table's entries

    def _entry_language(self) -> None:
        found = {language_of(str(item.get("module", item.get("file")))) for item in self.table.entries} | {"python"}
        if found != {"python"}:
            ordered = ", ".join(lang_id for lang_id in language_ids() if lang_id in found)
            raise MapError(message("refactor.map-mixed-languages", map=self.table.raw, languages=ordered))

    def _key_at(self, rel: str, offset: int) -> Key:
        """The canonical key of the declaration at `offset`; the site itself where no rename locates one."""
        try:
            return self.locator.at(rel, offset).key
        except RefactorError:
            return ("site", rel, offset)

    def _entry_keys(self, item: dict[str, Any]) -> list[Key]:
        """The symbols a table entry locates; `MapError` with its locator's finding when it locates none."""
        file = str(item.get("module", item.get("file")))
        try:
            rel = project_rel(self.root, str(self.root / file))
            if "module" in item:
                return [self.locator.file_module(rel).key]
            source = self.session.snapshot.source(rel)
            symbol = item.get("symbol")
            if is_wildcard(symbol) and "new_name" in item:
                return [self._key_at(rel, located.offset) for located in locate_all(source, str(symbol), file)]
            locator = Locator(symbol=symbol, line=item.get("line"), col=item.get("col"), offset=item.get("offset"))
            offset, _ = resolve(locator, source, file)
        except OSError:
            raise MapError(message("refactor.source-missing", path=file)) from None
        except RefactorError as exc:
            raise MapError(str(exc)) from None
        if literal_member_at(source, offset) is not None:
            return [("literal", rel, offset)]
        return [self._key_at(rel, offset)]

    # ---- candidates

    def _file_candidates(self, rel: str) -> list[Candidate]:
        """Each symbol `rel` declares under a name holding a word, in source order, an import by its `as` name only;
        a lambda's parameter is listed instead."""
        source = self.session.snapshot.source(rel)
        module = self.locator.module(rel)
        if module is None:
            return []
        reached: set[int] = set()
        found = self._path_candidates(rel, source, reached)
        for _, name, node in module.binder.bound:
            offset = bound_at(source, node, name)
            words = held_words(name, self.table.words)
            if offset is None or offset in reached or not words or _plain_import(node):
                continue
            reached.add(offset)
            if isinstance(node, ast.arg) and isinstance(source.parent(source.parent(node) or node), ast.Lambda):
                line = source.line(offset)
                self.listed += [(rel, line, offset, message("refactor.not-generated", path=rel, line=line, name=name,
                                                            word=word)) for word in words]
                continue
            found.append(Candidate(rel=rel, name=name, key=self._key_at(rel, offset), offset=offset, offsets=(offset,)))
        out: dict[Key, Candidate] = {}
        for candidate in sorted(found, key=lambda c: c.offset or 0):
            out.setdefault(candidate.key, candidate)
        return list(out.values())

    def _path_candidates(self, rel: str, source: SourceFile, reached: set[int]) -> list[Candidate]:
        """The candidates a symbol path reaches, their offsets added to `reached`."""
        paths: dict[str, list[list[tuple[str, int, ast.AST]]]] = {}
        for path, group in declared_paths(source):
            paths.setdefault(path, []).append(group)
        found: list[Candidate] = []
        for path, groups in paths.items():
            for group in groups:
                reached.update(offset for _, offset, _ in group)
                own = [d for d in group if not _plain_import(d[2])]
                if not own or not held_words(own[0][0], self.table.words):
                    continue
                exact = len(groups) == 1 and own[0] is group[0]
                found.append(Candidate(rel=rel, name=own[0][0], key=self._key_at(rel, own[0][1]), offset=own[0][1],
                                       offsets=tuple(d[1] for d in own), path=path if exact else None))
        return found

    def _modules(self, rels: list[str]) -> list[Candidate]:
        """Each module file, and each package by its `__init__.py`, whose name holds a word."""
        out: list[Candidate] = []
        for rel in rels:
            path = Path(rel)
            package = path.stem == _INIT
            name = path.parent.name if package else path.stem
            if name and held_words(name, self.table.words):
                out.append(Candidate(rel=rel, name=name, key=self.locator.file_module(rel).key))
        return out

    # ---- the map

    def _new_name(self, candidate: Candidate, source: SourceFile | None) -> str | None:
        """The candidate's new name, each word a carve-out keeps listed; None when none remains."""
        kept = self.carves.carved(candidate.rel, candidate.name, candidate.offsets, module=source is None)
        offset = candidate.offset or 0
        line = source.line(offset) if source is not None else 1
        self.listed += [(candidate.rel, line, offset, message(
            "refactor.carved", path=candidate.rel, line=line, name=candidate.name, word=word, matcher=label))
            for word, label in kept]
        new = replace_words(candidate.name, self.table.words, frozenset(word for word, _ in kept))
        return new if new != candidate.name else None

    def _joined(self, rel: str, source: SourceFile, whole: dict[Key, str]) -> set[str]:
        """The local names of `rel` one wildcard entry stands for: two or more locals, every one in `whole` (written
        by its path, no word kept)."""
        out: set[str] = set()
        for name in set(whole.values()):
            keys = [self._key_at(rel, found.offset) for found in locate_all(source, f"{WILDCARD}.{LOCALS}.{name}", rel)]
            if len(keys) > 1 and all(whole.get(key) == name for key in keys):
                out.add(name)
        return out

    def _file_entries(self, rel: str, candidates: list[Candidate]) -> list[dict[str, Any]]:
        """The entries of a file's declarations in source order, same-named locals as one wildcard entry at the
        first."""
        source = self.session.snapshot.source(rel)
        written, whole = self._written(candidates, source)
        joined = self._joined(rel, source, whole)
        out: list[dict[str, Any]] = []
        done: set[str] = set()
        for c, new, local in written:
            if local is None or local not in joined or c.key not in whole:
                out.append(_entry(source, c, new))
            elif local not in done:
                out.append({"file": rel, "symbol": f"{WILDCARD}.{LOCALS}.{local}", "new_name": new})
                done.add(local)
        return out

    def _written(self, candidates: list[Candidate],
                 source: SourceFile) -> tuple[list[tuple[Candidate, str, str | None]], dict[Key, str]]:
        """Each candidate that is written, with its new name and its name as a function local; and the locals written
        with no word kept, by key."""
        written: list[tuple[Candidate, str, str | None]] = []
        whole: dict[Key, str] = {}
        for c in candidates:
            carved = len(self.listed)
            new = self._new_name(c, source)
            if new is None:
                continue
            m = _LOCAL.fullmatch(c.path) if c.path is not None else None
            local = m.group(1) if m is not None else None
            written.append((c, new, local))
            if local is not None and len(self.listed) == carved:
                whole[c.key] = local
        return written, whole

    def run(self) -> int:
        """Print the map and the listings; 1 with `refactor.generate-empty` when the map is empty."""
        self._entry_language()
        self.carves.resolve()
        located = {key for item in self.table.entries for key in self._entry_keys(item)}
        rels = self.session.python_files()
        entries = list(self.table.entries)
        modules = {c.rel: c for c in self._modules(self.session.all_python_files()) if c.key not in located}
        for rel in sorted({*rels, *modules}):
            new = self._new_name(modules[rel], None) if rel in modules else None
            if new is not None:
                entries.append({"module": rel, "new_name": new})
            if rel in rels:
                entries += self._file_entries(rel, [c for c in self._file_candidates(rel) if c.key not in located])
        for _, _, _, text in sorted(self.listed):
            print(text, file=sys.stderr)
        if not entries:
            print(message("refactor.generate-empty", table=self.table.raw), file=sys.stderr)
            return 1
        print("\n".join(_line(item) for item in entries))
        return 0


def generate_map(root: Path, table: str) -> int:
    """Print TABLE's rename map for the Python sources under `root`; 1 when it is empty. `MapError` and `LocatorError`
    (exit 2) for an invalid table, an entry of another language or a locator that names nothing."""
    return Generator(root, load_table(table)).run()
