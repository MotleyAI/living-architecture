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
    line_start,
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
        self.olds = project.names(source)
        self.old = self.olds[0]
        self.new = project.dotted(dest)
        self.region = moved.region
        self.values = {("decl", f"{old}@{key}") for old in self.olds for key in moved.keys}
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
            if not isinstance(stmt, ast.ImportFrom) or file.binder.from_module(stmt) not in self.olds:
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
        for node, scope in file.attributes:
            if not self._through_old(file, node, scope):
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
                stars += [s for s in file.binder.star_nodes if file.binder.from_module(s) in self.olds]
        for stmt in dict.fromkeys(stars):
            file.after.append((stmt, f"from {from_name(stmt, file.package, self.new)} import {self.name}"))

    # ---- the source

    def _inside(self, file: File, node: ast.expr) -> bool:
        return self.region[0] <= file.offset(node) < self.region[1]

    def _through_old(self, file: File, node: ast.Attribute, scope: Scope) -> bool:
        """`node` reads the moved symbol through its old module."""
        value = file.resolve(scope, node.value)
        return node.attr == self.name and value is not None and value[0] == "module" and value[1] in self.olds

    def _source_edits(self, file: File) -> None:
        file.edits.add(self.region[0], self.region[1], "")
        top = file.top
        bare = any(n.id == self.name and file.lookup(s, self.name) is top and not self._inside(file, n) for n, s in file.names)
        dotted = any(self._through_old(file, n, s) and not self._inside(file, n) for n, s in file.attributes)
        if bare or dotted:
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
            if file.obj(node) not in {f"{old}.{self.name}" for old in self.olds}:
                raise NameConflict(self.name, file.rel, file.line(node))
        roots = {id(_root(node)) for node in self._self_uses()}
        needed = needed_imports(self.origin, self.moved, self.old, self.new, roots)
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

    def _self_uses(self) -> list[ast.Attribute]:
        """The moved code's dotted uses of the symbol through its old module that run once the symbol is bound: in a
        function or lambda, or after the first declaration; `NameConflict` where its bare name is bound locally."""
        origin = self.origin
        bound_at = origin.span(self.moved.statements[0])[1]
        found: list[ast.Attribute] = []
        for node, scope in origin.attributes:
            if not self._inside(origin, node) or not self._through_old(origin, node, scope):
                continue
            if not _deferred(scope) and origin.offset(node) < bound_at:
                continue
            owner = origin.lookup(scope, self.name)
            if owner is not None and owner is not origin.top:
                raise NameConflict(self.name, origin.rel, origin.line(origin.bound[owner][self.name][0]))
            found.append(node)
        return found

    def moved_text(self, newline: str) -> str:
        """The region's text, its relative imports recomputed for the destination and its dotted self-uses bare, ending
        in one line break."""
        origin = self.origin
        start, end = self.region
        edits = Edits(origin.text[start:end])
        for node in self._self_uses():
            use_start, use_end = origin.span(node)
            edits.add(use_start - start, use_end - start, self.name)
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
        """After the destination's own top-level import of the symbol, else after the last top-level import (or added
        import), else after the docstring, else after the leading comments; and after every destination statement
        binding a name the moved code reads while it is defined."""
        newline = newline_of(file.text)
        at, prefix = self._insertion_point(file, block, newline)
        own = self._own_import(file)
        if own is not None and self._read_before(file, own, at):
            start, end = file.span(own)
            rest = file.text[end : after_line(file.text, end)].strip()
            head = line_start(file.text, start)
            if rest and not rest.startswith("#") and (block is None or block <= head):
                file.edits.add(head, head, self.moved_text(newline) + newline * 2)
                return
            at, prefix = max(after_line(file.text, end), block or 0), newline * 2
        needed = self._after_dependencies(file)
        if needed is not None and needed > at:
            at, prefix = needed, newline * 2
        file.edits.add(at, at, prefix + self.moved_text(newline))

    def _own_import(self, file: File) -> ast.ImportFrom | None:
        """The destination's first import of the symbol from the source directly in its module body."""
        return next((s for s in _body(file) if isinstance(s, ast.ImportFrom) and file.binder.from_module(s) in self.olds
                     and any(a.name == self.name for a in s.names)), None)

    def _read_before(self, file: File, own: ast.ImportFrom, end: int) -> bool:
        """A destination statement after `own` and before `end` reads a name `own` binds the symbol to while it runs."""
        names = {a.asname or a.name for a in own.names if a.name == self.name}
        start = file.span(own)[1]
        return any(n.id in names and not _deferred(scope) and start <= file.offset(n) < end for n, scope in file.names)

    def _insertion_point(self, file: File, block: int | None, newline: str) -> tuple[int, str]:
        body = _body(file)
        tops = [s for s in body if isinstance(s, (ast.Import, ast.ImportFrom))]
        if tops or block is not None:
            return max(after_line(file.text, file.span(tops[-1])[1]) if tops else 0, block or 0), newline * 2
        if body and is_docstring(body[0]):
            return after_line(file.text, file.span(body[0])[1]), newline * 2
        lines = split_lines(file.text)
        comments = 0
        while comments < len(lines) and lines[comments].lstrip().startswith("#") and _more(lines, comments):
            comments += 1
        return sum(len(line) for line in lines[:comments]), newline * 2 if comments else ""

    def _after_dependencies(self, file: File) -> int | None:
        """The end of the last top-level destination statement binding a name the moved code reads while it is
        defined (bases, decorators, defaults, class bodies)."""
        origin = self.origin
        reads = {n.id for n, scope in origin.names
                 if self._inside(origin, n) and not _deferred(scope) and scope.resolving(n.id) is origin.top}
        bound = [file.offset(node) for scope, name, node in file.binder.bound
                 if name in reads and scope.owner(name) is file.top and not _deferred(scope)
                 and isinstance(node, (ast.stmt, ast.expr, ast.alias))]
        spans = [file.span(stmt) for stmt in _body(file)]
        return max((after_line(file.text, end) for start, end in spans if any(start <= b < end for b in bound)),
                   default=None)


def _deferred(scope: Scope | None) -> bool:
    """Code in `scope` runs only after the declarations around it exist: a function or lambda encloses it."""
    while scope is not None:
        if scope.kind == "function":
            return True
        scope = scope.parent
    return False


def _root(node: ast.expr) -> ast.expr:
    """The innermost receiver of an attribute chain."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node


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
