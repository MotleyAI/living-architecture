"""Python moves as minimal edits over each file's own text: la's static resolver finds and resolves each reference,
and every edit lands at a reference."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

from deterministic_refactor.refactor.move_project import MoveProject
from deterministic_refactor.refactor.python_source import SourceFile, header_end
from deterministic_refactor.refactor.static_resolver import ImportItem, Scope, Value

_BREAK = re.compile(r"\r\n|\r|\n")
_LINE_TAIL = re.compile(r"[ \t]*(?:#[^\r\n]*)?(?:\r\n|\r|\n)?")
_ITEM_TAIL = re.compile(r"[ \t]*(?:,[ \t]*)?(?:#[^\r\n]*)?(?:\r\n|\r|\n)?")
_SKIPPED_TOKENS = {tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT, tokenize.ENDMARKER, tokenize.INDENT, tokenize.DEDENT}

Positioned = ast.stmt | ast.expr | ast.alias


class NameConflict(Exception):
    """An added binding of `name` would shadow what `path`:`line` binds it to."""

    def __init__(self, name: str, path: str, line: int) -> None:
        super().__init__(name, path, line)
        self.name = name
        self.path = path
        self.line = line


def relative_module(importer: str, target: str) -> str:
    """The `from` module naming `target` from package `importer`: relative within one top-level package, else absolute."""
    here = importer.split(".") if importer else []
    there = target.split(".")
    if not here or here[0] != there[0]:
        return target
    common = 0
    while common < min(len(here), len(there)) and here[common] == there[common]:
        common += 1
    return "." * (len(here) - common + 1) + ".".join(there[common:])


def newline_of(text: str) -> str:
    """The line break `text` uses: its first one, else `\\n`."""
    found = _BREAK.search(text)
    return found.group() if found else "\n"


def after_line(text: str, pos: int) -> int:
    found = _BREAK.search(text, pos)
    return len(text) if found is None else found.end()


def line_start(text: str, pos: int) -> int:
    return max(text.rfind("\n", 0, pos), text.rfind("\r", 0, pos)) + 1


def span(source: SourceFile, node: Positioned) -> tuple[int, int]:
    start = source.offset(node.lineno, node.col_offset)
    return start, source.offset(node.end_lineno or node.lineno, node.end_col_offset or 0)


def named(aliases: list[ast.alias]) -> str:
    return ", ".join(f"{a.name} as {a.asname}" if a.asname else a.name for a in aliases)


def is_docstring(node: ast.stmt) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def block_end(source: SourceFile) -> int:
    """After the leading run of imports; without one, after the module docstring, else after the file's header."""
    body = source.tree.body if source.tree is not None else []
    end = header_end(source.text)
    index = 0
    if body and is_docstring(body[0]):
        end = after_line(source.text, span(source, body[0])[1])
        index = 1
    while index < len(body) and isinstance(body[index], (ast.Import, ast.ImportFrom)):
        end = after_line(source.text, span(source, body[index])[1])
        index += 1
    return end


def leading_block_end(text: str) -> int:
    """`block_end` of a module's text."""
    return block_end(SourceFile(Path(), text))


class Edits:
    """Pending character edits of one text, applied at once; inserted lines end with its line break."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.newline = newline_of(text)
        self._pending: list[tuple[int, int, int, str]] = []

    def add(self, start: int, end: int, new: str) -> None:
        if not any(e[0] == start and e[1] == end and e[3] == new for e in self._pending):
            self._pending.append((start, end, len(self._pending), new))

    def insert_line(self, pos: int, line: str) -> None:
        """`line` as its own line at line start `pos`, keeping a missing final newline missing."""
        line = line.replace("\n", self.newline)
        if pos == len(self.text) and self.text and not self.text.endswith(("\n", "\r")):
            self.add(pos, pos, self.newline + line)
        else:
            self.add(pos, pos, line + self.newline)

    def apply(self) -> str:
        out: list[str] = []
        cursor = 0
        for start, end, _, new in sorted(self._pending):
            if start < cursor:
                raise AssertionError(f"overlapping edits at {start}")
            out.append(self.text[cursor:start] + new)
            cursor = end
        return "".join(out) + self.text[cursor:]


class File:
    """One module's text, the resolver's scopes of it, and its pending edits."""

    def __init__(self, project: MoveProject, rel: str, package: str) -> None:
        module = project.module(rel)
        if module is None:
            raise SyntaxError(rel)
        self.project = project
        self.rel = rel
        self.source = project.snapshot.source(rel)
        self.text = self.source.text
        self.module = module
        self.binder = module.binder
        self.top = module.scope
        self.package = package
        self.edits = Edits(self.text)
        self.bound: defaultdict[Scope, dict[str, list[ast.AST]]] = defaultdict(dict)
        for scope, name, node in self.binder.bound:
            self.bound[scope.owner(name)].setdefault(name, []).append(node)
        self.names: list[tuple[ast.Name, Scope]] = []
        self.attributes: list[tuple[ast.Attribute, Scope]] = []
        self._loads()
        self.rewritten: set[int] = set()
        self.removed: set[int] = set()
        self.plain_now: dict[int, str] = {}
        self.uses_rewritten: dict[int, int] = {}
        self.needs: list[tuple[str, ast.AST | None, Scope]] = []
        self.after: list[tuple[ast.stmt, str]] = []
        self.anchored: set[int] = set()
        self.drops: dict[int, tuple[ast.Import | ast.ImportFrom, set[int]]] = {}

    def _loads(self) -> None:
        """Every name and attribute read, annotations included, with the scope it is read in."""
        found: list[tuple[ast.expr, Scope]] = list(self.binder.loads)
        for expr, scope in self.binder.annotations:
            found += [(n, scope) for n in ast.walk(expr) if isinstance(n, (ast.Name, ast.Attribute))]
        for node, scope in found:
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                self.names.append((node, scope))
            elif isinstance(node, ast.Attribute):
                self.attributes.append((node, scope))

    # ---- bindings

    def lookup(self, scope: Scope, name: str) -> Scope | None:
        """The scope binding `name` as read in `scope`, None when no scope does."""
        owner = scope.resolving(name)
        return owner if name in self.bound.get(owner, {}) else None

    def item(self, node: ast.AST) -> ImportItem | None:
        return self.binder.import_items.get(id(node)) if isinstance(node, ast.alias) else None

    def line(self, node: ast.AST) -> int:
        item = self.item(node)
        return item.stmt.lineno if item is not None else int(getattr(node, "lineno", 0))

    def obj(self, node: ast.AST) -> str | None:
        """The dotted object an import binds its name to; None for any other binding."""
        item = self.item(node)
        if item is None or not isinstance(node, ast.alias):
            return None
        if isinstance(item.stmt, ast.Import):
            return node.name if node.asname else node.name.split(".")[0]
        base = self.binder.from_module(item.stmt)
        return f"{base}.{node.name}" if base else None

    def plain(self, node: ast.AST) -> str | None:
        """The module an unaliased `import a.b` names (as rewritten); None for any other binding."""
        item = self.item(node)
        if item is None or not isinstance(item.stmt, ast.Import) or not isinstance(node, ast.alias) or node.asname:
            return None
        return self.plain_now.get(id(node), node.name)

    def uses(self, name: str, scope: Scope) -> int:
        return sum(1 for node, at in self.names if node.id == name and self.lookup(at, name) is scope)

    def offset(self, node: Positioned) -> int:
        return span(self.source, node)[0]

    # ---- token-level edits

    def span(self, node: Positioned) -> tuple[int, int]:
        return span(self.source, node)

    def tokens(self, node: ast.stmt) -> list[tuple[str, int, int]]:
        start, end = self.span(node)
        segment = self.text[start:end]
        starts = [0, *(m.end() for m in re.finditer("\n", segment))]
        return [
            (tok.string, start + starts[tok.start[0] - 1] + tok.start[1], start + starts[tok.end[0] - 1] + tok.end[1])
            for tok in tokenize.generate_tokens(io.StringIO(segment).readline)
            if tok.type not in _SKIPPED_TOKENS
        ]

    def comments(self, node: ast.stmt) -> list[str]:
        start, end = self.span(node)
        tokens = tokenize.generate_tokens(io.StringIO(self.text[start:end]).readline)
        return [tok.string for tok in tokens if tok.type == tokenize.COMMENT]

    def rewrite_module(self, stmt: ast.ImportFrom, new: str) -> None:
        tokens = self.tokens(stmt)
        cut = next(i for i, tok in enumerate(tokens) if i and tok[0] == "import")
        if not new:
            start, end = self.span(stmt)
            comments = "".join(f"  {c}" for c in self.comments(stmt))
            self.edits.add(start, end, f"import {named(stmt.names)}{comments}")
            return
        self.edits.add(tokens[1][1], tokens[cut - 1][2], new)

    def rewrite_dotted(self, stmt: ast.Import, index: int, new: str) -> None:
        start, end = self.span(stmt.names[index])
        name_end = start
        for text, tok_start, tok_end in self.tokens(stmt):
            if start <= tok_start < end:
                if text == "as":
                    break
                name_end = tok_end
        self.edits.add(start, name_end, new)

    def remove_item(self, stmt: ast.Import | ast.ImportFrom, index: int) -> None:
        self.drops.setdefault(id(stmt), (stmt, set()))[1].add(index)

    def _remove_items(self, stmt: ast.Import | ast.ImportFrom, items: set[int]) -> None:
        if len(items) == len(stmt.names):
            self.remove_stmt(stmt)
            return
        parenthesized = any(tok[0] == "(" for tok in self.tokens(stmt))
        self.remove_elements([self.span(alias) for alias in stmt.names], items, parenthesized)

    def remove_elements(self, spans: list[tuple[int, int]], indexes: set[int], bracketed: bool) -> None:
        """Remove some of a list's elements, each with its own comma; one alone on its line in brackets, with the line."""
        for first in sorted(i for i in indexes if i - 1 not in indexes):
            last = first
            while last + 1 in indexes:
                last += 1
            start, end = spans[first][0], spans[last][1]
            begin, stop = line_start(self.text, start), after_line(self.text, end)
            if bracketed and not self.text[begin:start].strip() and _ITEM_TAIL.fullmatch(self.text[end:stop]):
                self.edits.add(begin, stop, "")
            elif first:
                self.edits.add(spans[first - 1][1], end, "")
            elif last + 1 < len(spans):
                self.edits.add(start, spans[last + 1][0], "")
            else:
                comma = re.match(r"[ \t]*,", self.text[end:])
                self.edits.add(start, end + (comma.end() if comma else 0), "")

    def remove_stmt(self, stmt: ast.stmt) -> None:
        start, end = self.span(stmt)
        begin, stop = line_start(self.text, start), after_line(self.text, end)
        before = self.text[begin:start]
        if not before.strip() and _LINE_TAIL.fullmatch(self.text[end:stop]):
            self.edits.add(begin, stop, "")
        elif before.rstrip().endswith(";"):
            self.edits.add(self.text.rindex(";", begin, start), end, "")
        else:
            tail = re.match(r"[ \t]*;[ \t]*", self.text[end:])
            self.edits.add(start, end + (tail.end() if tail else 0), "")

    def insert_after(self, stmt: ast.stmt, line: str) -> None:
        """`line` as the statement after `stmt` in its suite: on the next line at its indentation, or after `; ` in an
        inline suite (one on its compound statement's header line)."""
        self.anchored.add(id(stmt))
        start, end = self.span(stmt)
        if self._inline(stmt):
            self.edits.add(end, end, f"; {line}")
            return
        indent = re.match(r"[ \t]*", self.text[line_start(self.text, start) :])
        self.edits.insert_line(after_line(self.text, end), (indent.group() if indent else "") + line)

    def _inline(self, stmt: ast.stmt) -> bool:
        """`stmt` sits in an inline suite: one starting on its header's line, after the header's `:`."""
        suite = self._suite(stmt)
        if not suite or suite[0].lineno != stmt.lineno:
            return False
        start = self.span(suite[0])[0]
        return self.text[line_start(self.text, start) : start].rstrip().endswith(":")

    def _suite(self, stmt: ast.stmt) -> list[ast.stmt]:
        """The statement list holding `stmt`, below the module body; empty at the top level."""
        tree = self.source.tree
        for node in ast.walk(tree) if tree is not None else ():
            for field in ("body", "orelse", "finalbody"):
                suite = getattr(node, field, None)
                if node is not tree and isinstance(suite, list) and any(s is stmt for s in suite):
                    return suite
        return []
    def rewrite_use(self, node: ast.Attribute | ast.Name, scope: Scope, new: str, needs: str | None, obj: str | None = None) -> None:
        """Rule 3: the chain `node` becomes `new`, its root free for `obj` (default: itself); `needs` is the module to
        import."""
        start, end = self.span(node)
        root: ast.expr = node
        while isinstance(root, ast.Attribute):
            root = root.value
        if not isinstance(root, ast.Name):
            return
        first = new.split(".")[0]
        self.check_free(first, obj or first, scope)
        found = self.lookup(scope, root.id)
        imports = self._imports(found, root.id)
        binding = self._latest(imports, root.lineno)
        self.edits.add(start, end, new)
        if binding is not None:
            self.uses_rewritten[id(binding)] = self.uses_rewritten.get(id(binding), 0) + 1
        if needs is not None:
            own = [b for b in imports if (item := self.item(b)) is not None and item.scope is found]
            place = self._latest(own, root.lineno)
            self.needs.append((needs, place, found if place is not None and found is not None else self.top))

    def root_rebound(self, scope: Scope, node: ast.Attribute | ast.Name) -> bool:
        """The chain's root is bound by a plain import this refactor rewrote to bind another name."""
        root: ast.expr = node
        while isinstance(root, ast.Attribute):
            root = root.value
        if not isinstance(root, ast.Name):
            return False
        binding = self._latest(self._imports(self.lookup(scope, root.id), root.id), root.lineno)
        target = self.plain_now.get(id(binding)) if binding is not None else None
        return target is not None and target.split(".")[0] != root.id

    def _imports(self, scope: Scope | None, name: str) -> list[ast.AST]:
        return [b for b in self.bound[scope][name] if self.item(b) is not None] if scope is not None else []

    def _latest(self, imports: list[ast.AST], line: int) -> ast.AST | None:
        """The last of `imports` written by `line`, else the last of them."""
        before = [b for b in imports if self.line(b) <= line]
        return (before or imports or [None])[-1]

    def resolve(self, scope: Scope, expr: ast.expr) -> Value:
        """`expr`'s value; a root bound outside any function or comprehension reads the last import written by its
        line, whatever else rebinds it there."""
        resolver = self.project.resolver
        if isinstance(expr, ast.Attribute):
            base = self.resolve(scope, expr.value)
            return resolver.member(base[1], expr.attr) if base is not None and base[0] == "module" else None
        owner = self.lookup(scope, expr.id) if isinstance(expr, ast.Name) else None
        latest = self._latest(self._imports(owner, expr.id), expr.lineno) if isinstance(expr, ast.Name) else None
        if owner is None or owner.kind in ("function", "comprehension") or not isinstance(latest, ast.alias):
            return resolver.resolve(self.module, scope, expr)
        item = self.item(latest)
        if item is not None and isinstance(item.stmt, ast.ImportFrom):
            return resolver.member(self.binder.from_module(item.stmt), latest.name)
        return ("module", self.obj(latest) or latest.name)

    def _scopes(self) -> Iterator[Scope]:
        seen: dict[int, Scope] = {id(self.top): self.top}
        for _, scope, _ in self.binder.imports:
            seen.setdefault(id(scope), scope)
        return iter(seen.values())

    def finish(self) -> str:
        """Remove imports whose every use was rewritten, add the imports rewritten uses need, and apply."""
        for scope in self._scopes():
            for name, nodes in self.bound.get(scope, {}).items():
                for node in nodes:
                    self._drop_if_all_rewritten(name, node, scope)
        self._add_needed_imports()
        for stmt, line in self.after:
            self.insert_after(stmt, line)
        gone = {id(stmt) for stmt, items in self.drops.values() if len(items) == len(stmt.names)} - self.anchored
        for stmt, items in self.drops.values():
            self._remove_items(stmt, items)
        self._fill_emptied(gone)
        return self.edits.apply()

    def _fill_emptied(self, gone: set[int]) -> None:
        """`pass` in each block whose every statement this refactor removes, so the block stays valid."""
        tree = self.source.tree
        for node in ast.walk(tree) if tree is not None and gone else ():
            for field in ("body", "orelse", "finalbody"):
                suite = getattr(node, field, None)
                if node is tree or not isinstance(suite, list) or not suite or any(id(s) not in gone for s in suite):
                    continue
                start = self.span(suite[0])[0]
                if self._inline(suite[0]):
                    self.edits.add(start, start, "pass")
                else:
                    indent = self.text[line_start(self.text, start) : start]
                    self.edits.insert_line(after_line(self.text, self.span(suite[-1])[1]), indent + "pass")

    def _drop_if_all_rewritten(self, name: str, node: ast.AST, scope: Scope) -> None:
        count = self.uses_rewritten.get(id(node), 0)
        item = self.item(node)
        named = any(name in s.nonlocals and s.owner(name) is scope for s in self.binder.scopes)
        if count and item is not None and id(item.stmt) not in self.rewritten and self.uses(name, scope) == count \
                and not named:
            self.removed.add(id(node))
            self.remove_item(item.stmt, item.index)

    def _add_needed_imports(self) -> None:
        added: set[tuple[str, int]] = set()
        for module, binding, scope in self.needs:
            item = self.item(binding) if binding is not None else None
            key = (module, id(item.stmt) if item is not None else 0)
            if key in added or self.binds_module(scope, module):
                continue
            added.add(key)
            self.check_free(module.split(".")[0], module.split(".")[0], scope)
            if item is not None:
                self.insert_after(item.stmt, f"import {module}")
            else:
                self.edits.insert_line(block_end(self.source), f"import {module}")

    def binds_module(self, scope: Scope, module: str) -> bool:
        root = module.split(".")[0]
        found = self.lookup(scope, root)
        if found is not None and any(
            id(b) not in self.removed and (plain := self.plain(b)) is not None
            and (plain == module or plain.startswith(module + "."))
            for b in self.bound[found][root]
        ):
            return True
        return any(self._rewritten_binds(alias, scope, module) for alias in self._rewritten_plain())

    def _rewritten_plain(self) -> Iterator[ast.alias]:
        for stmt, _, _ in self.binder.imports:
            if isinstance(stmt, ast.Import):
                yield from (a for a in stmt.names if id(a) in self.plain_now and id(a) not in self.removed)

    def _rewritten_binds(self, alias: ast.alias, scope: Scope, module: str) -> bool:
        """`alias`, a plain import rewritten under a new root, is visible from `scope` and binds `module`."""
        target = self.plain_now[id(alias)]
        if target != module and not target.startswith(module + "."):
            return False
        name = alias.name.split(".")[0]
        owner = self.lookup(scope, name)
        return owner is not None and any(b is alias for b in self.bound[owner][name])

    def check_free(self, name: str, obj: str, scope: Scope) -> None:
        """Refuse when `name` already resolves, from `scope`, to anything but `obj`."""
        found = self.lookup(scope, name)
        if found is None:
            return
        for node in self.bound[found][name]:
            if id(node) not in self.removed and self.obj(node) != obj:
                raise NameConflict(name, self.rel, self.line(node))


def from_name(stmt: ast.ImportFrom, package: str, target: str) -> str:
    """The module `stmt` names `target` by: in its own relative or absolute form."""
    return relative_module(package, target) if stmt.level else target
