"""`move-symbol` for Python: the moved code and the imports it needs, and each reference edited in place."""

from __future__ import annotations

import ast
from collections.abc import Iterator

from living_architecture.refactor.move_edits import (
    Edits,
    File,
    NameConflict,
    after_line,
    block_end,
    from_name,
    is_docstring,
    named,
    newline_of,
    relative_module,
)
from living_architecture.refactor.move_project import MoveProject
from living_architecture.refactor.moved_imports import (
    Needed,
    Statement,
    is_type_checking,
    needed_imports,
    ordered,
)
from living_architecture.refactor.moved_symbol import MovedSymbol
from living_architecture.refactor.python_source import split_lines
from living_architecture.refactor.static_resolver import Scope

_INDENT = "    "


class SymbolMove:
    """One `move-symbol` of `moved` from file `source` to file `dest`, and the per-file edits of its references."""

    def __init__(self, project: MoveProject, source: str, moved: MovedSymbol, dest: str) -> None:
        self.project = project
        self.source = source
        self.dest = dest
        self.moved = moved
        self.name = moved.name
        self.old = project.dotted(source)
        self.new = project.dotted(dest)
        self.region = moved.region
        self.values = {("decl", f"{self.old}@{key}") for key in moved.keys}
        self.origin = File(project, source, project.package(source))

    def edit(self, rel: str) -> str | None:
        """`rel`'s text after the move's edits; None when the file holds nothing to edit."""
        if rel not in (self.source, self.dest) and self.name not in self.project.snapshot.text(rel):
            return None
        if self.project.module(rel) is None:
            return None
        file = File(self.project, rel, self.project.package(rel))
        is_dest = rel == self.dest
        self._importers(file, is_dest)
        if rel == self.source:
            self._source_edits(file)
        else:
            self._rewrite_uses(file, is_dest)
        if is_dest:
            self._dest_edits(file)
        return file.finish()

    # ---- importers

    def _importers(self, file: File, is_dest: bool) -> None:
        for stmt, scope, _ in file.binder.imports:
            if not isinstance(stmt, ast.ImportFrom) or file.binder.from_module(stmt) != self.old:
                continue
            hits = [i for i, alias in enumerate(stmt.names) if alias.name == self.name]
            if not hits:
                continue
            _move_items(file, stmt, hits, None if is_dest else from_name(stmt, file.package, self.new))
            if is_dest:
                self._unalias(file, stmt, hits, scope)

    def _unalias(self, file: File, stmt: ast.ImportFrom, hits: list[int], scope: Scope) -> None:
        """Destination: free the removed import's names; each use of an alias it bound becomes the symbol's name."""
        obj = f"{self.old}.{self.name}"
        for hit in hits:
            file.removed.add(id(stmt.names[hit]))
        for alias in {a for i in hits if (a := stmt.names[i].asname) and a != self.name}:
            owner = scope.owner(alias)
            mine = {id(stmt.names[i]) for i in hits}
            other = next((b for b in file.bound[owner][alias] if id(b) not in mine), None)
            if other is not None:
                raise NameConflict(alias, file.rel, file.line(other))
            for node, at in file.names:
                if node.id == alias and file.lookup(at, alias) is owner:
                    file.check_free(self.name, obj, at)
                    file.edits.add(*file.span(node), self.name)

    def _rewrite_uses(self, file: File, is_dest: bool) -> None:
        resolver = self.project.resolver
        for node, scope in file.attributes:
            if node.attr != self.name or resolver.resolve(file.module, scope, node.value) != ("module", self.old):
                continue
            if is_dest:
                file.rewrite_use(node, scope, self.name, None, f"{self.old}.{self.name}")
            else:
                file.rewrite_use(node, scope, f"{self.new}.{self.name}", self.new)
        if not is_dest:
            self._import_past_stars(file)

    def _import_past_stars(self, file: File) -> None:
        """After each star import of the source that a use of the name reads it through, import it from `new`."""
        stars: list[ast.ImportFrom] = []
        for node, scope in file.names:
            if node.id != self.name or file.lookup(scope, self.name) is not None:
                continue
            values = self.project.resolver.values(file.module, scope, node)
            if values and all(v in self.values for v in values):
                stars += [s for s in file.binder.star_nodes if file.binder.from_module(s) == self.old]
        for stmt in dict.fromkeys(stars):
            file.after.append((stmt, f"from {from_name(stmt, file.package, self.new)} import {self.name}"))

    # ---- the source

    def _inside(self, file: File, node: ast.expr) -> bool:
        return self.region[0] <= file.offset(node) < self.region[1]

    def _source_edits(self, file: File) -> None:
        file.edits.add(self.region[0], self.region[1], "")
        top = file.top
        if any(n.id == self.name and file.lookup(s, self.name) is top and not self._inside(file, n) for n, s in file.names):
            file.edits.insert_line(block_end(file.source), f"from {self.new} import {self.name}")
        for elements in _all_literals(file.source.tree):
            hits = {i for i, e in enumerate(elements) if isinstance(e, ast.Constant) and e.value == self.name}
            if hits:
                file.remove_elements([file.span(e) for e in elements], hits, True)
        self._drop_moved_only_imports(file)

    def _drop_moved_only_imports(self, file: File) -> None:
        """Remove the source's top-level imports that only the moved code reads."""
        top = file.top
        for name, nodes in file.bound[top].items():
            for node in nodes:
                item = file.item(node)
                if item is None or id(item.stmt) in file.rewritten or item.guard is not None or item.scope is not top:
                    continue
                uses = [n for n, at in file.names if n.id == name and file.lookup(at, name) is top]
                inside = [n for n in uses if self._inside(file, n)]
                if inside and len(inside) == len(uses):
                    file.remove_item(item.stmt, item.index)

    # ---- the destination

    def _dest_edits(self, file: File) -> None:
        for node in file.bound[file.top].get(self.name, []):
            if file.obj(node) != f"{self.old}.{self.name}":
                raise NameConflict(self.name, file.rel, file.line(node))
        needed = needed_imports(self.origin, self.moved, self.old, self.new)
        at = block_end(file.source)
        added = self._future(file, needed)
        checking = [part for stmt in needed.checking for line in _needed(file, stmt) for part in line.split("\n")]
        block = next((s for s in _body(file) if isinstance(s, ast.If) and is_type_checking(s)), None)
        regular = needed.regular
        if checking and block is None and not _binds(file, "TYPE_CHECKING"):
            regular = ordered(self.origin, [*regular, Statement("typing", [("TYPE_CHECKING", None)])], self.new)
        lines = [line for stmt in regular for line in _needed(file, stmt)]
        for line in lines:
            file.edits.insert_line(at, line)
        _insert_checking(file, at, block, checking)
        self._insert_moving(file, at if lines or checking or added else None)

    def _future(self, file: File, needed: Needed) -> bool:
        """Add the source's `__future__` imports the destination lacks as its first statement; whether any was added."""
        have = {a.name for s in _body(file) if isinstance(s, ast.ImportFrom) and s.module == "__future__" for a in s.names}
        body = _body(file)
        if body and is_docstring(body[0]):
            at = after_line(file.text, file.span(body[0])[1])
        else:
            at = file.span(body[0])[0] if body else 0
        added = False
        for stmt in needed.future:
            names = [pair for pair in stmt.names if pair[0] not in have]
            if names:
                file.edits.insert_line(at, stmt.text(names))
                have.update(n for n, _ in names)
                added = True
        return added

    def moved_text(self, newline: str) -> str:
        """The region's text, its relative imports recomputed for the destination, ending in one line break."""
        origin = self.origin
        start, end = self.region
        edits = Edits(origin.text[start:end])
        package = self.project.package(self.dest)
        for stmt, _, _ in origin.binder.imports:
            at = origin.span(stmt)[0]
            base = origin.binder.from_module(stmt) if isinstance(stmt, ast.ImportFrom) else None
            if not isinstance(stmt, ast.ImportFrom) or not stmt.level or not start <= at < end or base is None:
                continue
            target = relative_module(package, base)
            if target != "." * stmt.level + (stmt.module or ""):
                tokens = origin.tokens(stmt)
                cut = next(i for i, tok in enumerate(tokens) if i and tok[0] == "import")
                edits.add(tokens[1][1] - start, tokens[cut - 1][2] - start, target)
        text = edits.apply().rstrip() + "\n"
        return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline)

    def _insert_moving(self, file: File, block: int | None) -> None:
        """After the last top-level import (or added import), else after the docstring, else after the leading
        comments."""
        newline = newline_of(file.text)
        moving = self.moved_text(newline)
        body = _body(file)
        tops = [s for s in body if isinstance(s, (ast.Import, ast.ImportFrom))]
        if tops or block is not None:
            at = max(after_line(file.text, file.span(tops[-1])[1]) if tops else 0, block or 0)
            file.edits.add(at, at, newline * 2 + moving)
            return
        if body and is_docstring(body[0]):
            at = after_line(file.text, file.span(body[0])[1])
            file.edits.add(at, at, newline * 2 + moving)
            return
        lines = split_lines(file.text)
        comments = 0
        while comments < len(lines) and lines[comments].lstrip().startswith("#") and _more(lines, comments):
            comments += 1
        at = sum(len(line) for line in lines[:comments])
        file.edits.add(at, at, (newline * 2 if comments else "") + moving)


def _insert_checking(file: File, at: int, block: ast.If | None, checking: list[str]) -> None:
    """Add the `checking` lines to the destination's `if TYPE_CHECKING:` block, or to a new one at `at`."""
    if not checking:
        return
    if block is not None:
        for line in checking:
            file.insert_after(block.body[-1], line)
        return
    file.edits.insert_line(at, "if TYPE_CHECKING:")
    for line in checking:
        file.edits.insert_line(at, _INDENT + line)


def _more(lines: list[str], index: int) -> bool:
    """A line follows `index`, or `index` ends with a line break."""
    return index + 1 < len(lines) or lines[index].endswith(("\n", "\r"))


def _body(file: File) -> list[ast.stmt]:
    return file.source.tree.body if file.source.tree is not None else []


def _binds(file: File, name: str) -> bool:
    return any(id(node) not in file.removed for node in file.bound[file.top].get(name, []))


def _needed(file: File, stmt: Statement) -> list[str]:
    """`stmt` cut to the names the destination does not bind already; a name it binds to something else refuses."""
    if stmt.star:
        return [stmt.text()]
    keep: list[tuple[str, str | None]] = []
    for pair in stmt.names:
        bound, obj = stmt.bound(pair)
        live = _binds(file, bound)
        if live:
            file.check_free(bound, obj, file.top)
        plain_unbound = stmt.module is None and not pair[1] and not file.binds_module(file.top, pair[0])
        if not live or plain_unbound:
            keep.append(pair)
    return [stmt.lines(keep)] if keep else []


def _move_items(file: File, stmt: ast.ImportFrom, hits: list[int], target: str | None) -> None:
    """Point the `hits` items of `stmt` at `target`, or drop them when `target` is None."""
    if target is not None and len(hits) == len(stmt.names):
        file.rewrite_module(stmt, target)
    else:
        for hit in hits:
            file.remove_item(stmt, hit)
        if target is not None:
            file.after.append((stmt, f"from {target} import {named([stmt.names[i] for i in hits])}"))
    file.rewritten.add(id(stmt))


def _literals(value: ast.expr | None) -> Iterator[list[ast.expr]]:
    if isinstance(value, (ast.List, ast.Tuple)):
        yield value.elts
    elif isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add):
        yield from _literals(value.left)
        yield from _literals(value.right)


def _all_literals(tree: ast.Module | None) -> Iterator[list[ast.expr]]:
    """The list and tuple literals of the top-level `__all__` assignments, augmented assignments and `+` operands."""
    for stmt in tree.body if tree is not None else []:
        if isinstance(stmt, ast.Assign):
            targets, value = stmt.targets, stmt.value
        elif isinstance(stmt, ast.AnnAssign) or (isinstance(stmt, ast.AugAssign) and isinstance(stmt.op, ast.Add)):
            targets, value = [stmt.target], stmt.value
        else:
            continue
        if any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
            yield from _literals(value)


def symbol_move_texts(project: MoveProject, source: str, moved: MovedSymbol, dest: str) -> dict[str, str]:
    """Each file's new text where the move changes it."""
    move = SymbolMove(project, source, moved, dest)
    texts: dict[str, str] = {}
    for rel in project.files():
        text = move.edit(rel)
        if text is not None and text != project.snapshot.text(rel):
            texts[rel] = text
    return texts
