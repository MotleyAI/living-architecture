"""The imports a retarget adds, planned once across a map's entries: one import per block and home, joining an earlier
import from the home, else replacing the alias's import in place, else a new statement after it."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable

from living_architecture.refactor.python_source import SourceFile, split_lines
from living_architecture.refactor.rename_union import Session
from living_architecture.refactor.retarget import (
    ImportNeed,
    aliases_removal,
    block_of,
    imported_module,
    package_of,
)
from living_architecture.refactor.text_edits import TextEdit

_FROM = re.compile(r"from\s+")
_IMPORT = re.compile(r"\bimport\b")


def module_span(text: str, start: int) -> tuple[int, int]:
    """The module spelling of the `from ... import` statement at `start`, without the whitespace around it."""
    head = _FROM.match(text, start)
    assert head is not None
    keyword = _IMPORT.search(text, head.end())
    assert keyword is not None
    return head.end(), head.end() + len(text[head.end():keyword.start()].rstrip())


def spelled(home: str, package: str, relative: bool) -> str:
    """`home` as an import from `package` spells it: relative when `relative` and they share a top package."""
    if not relative:
        return home
    pkg, parts = package.split(".") if package else [], home.split(".")
    common = 0
    for ours, theirs in zip(pkg, parts):
        if ours != theirs:
            break
        common += 1
    return home if common == 0 else "." * (len(pkg) - common + 1) + ".".join(parts[common:])


def _named(exported: str, local: str) -> str:
    return exported if exported == local else f"{exported} as {local}"


def _unique(pairs: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    return list(dict.fromkeys(pairs))


class _File:
    """One file's needs, planned block by block."""

    def __init__(self, session: Session, rel: str, needs: list[ImportNeed]) -> None:
        self.session = session
        self.rel = rel
        self.source: SourceFile = session.snapshot.source(rel)
        assert self.source.tree is not None
        self.parents = {c: n for n in ast.walk(self.source.tree) for c in ast.iter_child_nodes(n)}
        self.needs = sorted(needs, key=self._position)
        self.leaving = {id(n.leaving): n for n in needs if n.leaving is not None}
        self.in_place: set[int] = set()
        self.duplicates: dict[int, tuple[ast.alias, int]] = {}
        self.edits: list[tuple[int, TextEdit]] = []
        self.entry = 0

    def _position(self, need: ImportNeed) -> tuple[int, int]:
        at = need.leaving if need.leaving is not None else need.anchor
        return self.source.offset(need.anchor.lineno, need.anchor.col_offset), self.source.offset(at.lineno, at.col_offset)

    def _push(self, edit: TextEdit, entry: int | None = None) -> None:
        self.edits.append((self.entry if entry is None else entry, edit))

    def plan(self) -> list[tuple[int, TextEdit]]:
        blocks: dict[int, list[ImportNeed]] = {}
        for need in self.needs:
            blocks.setdefault(id(block_of(self.parents, need.anchor)), []).append(need)
        for block_needs in blocks.values():
            homes: dict[str, list[ImportNeed]] = {}
            for need in block_needs:
                homes.setdefault(need.home.module, []).append(need)
            for module, group in homes.items():
                binding = [n for n in group if n.bind]
                self._place(module, binding)
                self.duplicates.update({id(d): (d, n.entry) for n in binding for d in n.duplicates})
        for stmt, removed in self._removals():
            for e in aliases_removal(self.source, self.rel, stmt, set(removed)):
                self._push(e, min(removed.values()))
        return self.edits

    def _removals(self) -> list[tuple[ast.ImportFrom, dict[int, int]]]:
        """Each statement losing names: the names' ids, each with the entry that drops it."""
        by_stmt: dict[int, tuple[ast.ImportFrom, dict[int, int]]] = {}
        for need in self.needs:
            if need.leaving is not None and id(need.anchor) not in self.in_place:
                assert isinstance(need.anchor, ast.ImportFrom)
                by_stmt.setdefault(id(need.anchor), (need.anchor, {}))[1][id(need.leaving)] = need.entry
        for key, (alias, entry) in self.duplicates.items():
            stmt = self.parents[alias]
            assert isinstance(stmt, ast.ImportFrom)
            by_stmt.setdefault(id(stmt), (stmt, {}))[1][key] = entry
        return list(by_stmt.values())

    def _place(self, module: str, group: list[ImportNeed]) -> None:
        if not group:
            return
        self.entry = group[0].entry
        first = group[0].anchor
        names = _unique((n.home.exported, n.local) for n in group)
        joined = self._join_target(module, first)
        if joined is not None:
            self._append(joined, names)
        elif self._replaceable(first, module):
            self._replace(first, module, names)
        else:
            self._insert_after(first, module, names)

    def _join_target(self, module: str, anchor: ast.stmt) -> ast.ImportFrom | None:
        """An earlier import of `anchor`'s block from `module`, none of whose names leave."""
        for stmt in block_of(self.parents, anchor):
            if stmt is anchor:
                return None
            if (isinstance(stmt, ast.ImportFrom) and imported_module(self.session, self.rel, stmt) == module
                    and all(a.name != "*" and id(a) not in self.leaving for a in stmt.names)):
                return stmt
        return None

    def _replaceable(self, stmt: ast.stmt, module: str) -> bool:
        """Every name of `stmt` leaves it for `module`, and it is not replaced for another module."""
        return (isinstance(stmt, ast.ImportFrom) and id(stmt) not in self.in_place
                and all(id(a) in self.leaving and self.leaving[id(a)].home.module == module for a in stmt.names))

    def _append(self, stmt: ast.ImportFrom, names: list[tuple[str, str]]) -> None:
        present = {(a.name, a.asname or a.name) for a in stmt.names}
        added = [p for p in names if p not in present]
        if added:
            end = self.source.span(stmt.names[-1])[1]  # pyright: ignore[reportArgumentType]
            self._push(TextEdit(path=self.rel, start=end, end=end, new_text="".join(f", {_named(*p)}" for p in added)))

    def _replace(self, stmt: ast.stmt, module: str, names: list[tuple[str, str]]) -> None:
        """`stmt`'s module and names rewritten in place; names it lacks appended."""
        assert isinstance(stmt, ast.ImportFrom)
        self.in_place.add(id(stmt))
        start, end = module_span(self.source.text, self.source.span(stmt)[0])
        home = spelled(module, package_of(self.session, self.rel), stmt.level > 0)
        self._push(TextEdit(path=self.rel, start=start, end=end, new_text=home))
        written: set[tuple[str, str]] = set()
        for alias in stmt.names:
            need = self.leaving[id(alias)]
            start = self.source.offset(alias.lineno, alias.col_offset)
            text = need.home.exported if alias.asname is not None else _named(need.home.exported, need.local)
            self._push(TextEdit(path=self.rel, start=start, end=start + len(alias.name), new_text=text), need.entry)
            written.add((need.home.exported, need.local))
        rest = [p for p in names if p not in written]
        if rest:
            end = self.source.span(stmt.names[-1])[1]  # pyright: ignore[reportArgumentType]
            self._push(TextEdit(path=self.rel, start=end, end=end, new_text="".join(f", {_named(*p)}" for p in rest)))

    def _insert_after(self, anchor: ast.stmt, module: str, names: list[tuple[str, str]]) -> None:
        """A new import statement on the line after `anchor`, at its indentation; right after it, `;`-separated, where
        `anchor` shares its line with a compound statement's header or a later statement."""
        source = self.source
        line_start = source.line_start(anchor.lineno)
        start, end = source.span(anchor)
        head = source.text[line_start:start]
        relative = isinstance(anchor, ast.ImportFrom) and anchor.level > 0
        home = spelled(module, package_of(self.session, self.rel), relative)
        statement = f"from {home} import {', '.join(_named(*p) for p in names)}"
        line = split_lines(source.text)[(anchor.end_lineno or anchor.lineno) - 1]
        ending = line[len(line.rstrip("\r\n")):]
        at = source.line_start(anchor.end_lineno or anchor.lineno) + len(line) - len(ending)
        if head.strip() or source.text[end:at].lstrip().startswith(";"):
            self._push(TextEdit(path=self.rel, start=end, end=end, new_text=f"; {statement}"))
        else:
            self._push(TextEdit(path=self.rel, start=at, end=at, new_text=(ending or "\n") + head + statement))


def plan_imports(session: Session, needs: list[ImportNeed]) -> list[tuple[int, TextEdit]]:
    """The edits binding every need's target and dropping the alias from the imports it leaves, each with the entry it
    comes from."""
    by_file: dict[str, list[ImportNeed]] = {}
    for need in needs:
        by_file.setdefault(need.path, []).append(need)
    return [e for rel in sorted(by_file) for e in _File(session, rel, by_file[rel]).plan()]
