"""Python moves as minimal edits: rope finds and resolves each occurrence, and every edit lands at a reference."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections.abc import Iterator
from typing import cast

from rope.base import libutils, pynames, pyobjects
from rope.base.change import ChangeContents, ChangeSet, MoveResource
from rope.base.project import Project
from rope.base.resources import File, Folder, Resource
from rope.refactor import occurrences
from rope.refactor.importutils.importinfo import FromImport, ImportInfo
from rope.refactor.move import MoveGlobal, MoveModule

from living_architecture.refactor.rope_patches import char_offset

_CHAIN = re.compile(r"[^\W\d]\w*(?:\s*\.\s*[^\W\d]\w*)+")
_LINE_TAIL = re.compile(r"[ \t]*(?:#[^\n]*)?\n?")
_ITEM_TAIL = re.compile(r"[ \t]*(?:,[ \t]*)?(?:#[^\n]*)?\n?")
_INIT = "__init__.py"
_SKIPPED_TOKENS = {tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT, tokenize.ENDMARKER, tokenize.INDENT, tokenize.DEDENT}


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


def _absolute(level: int, module: str, package: str) -> str | None:
    if not level:
        return module
    parts = package.split(".") if package else []
    if level - 1 > len(parts):
        return None
    return ".".join([*parts[: len(parts) - level + 1], *([module] if module else [])])


def _after_line(text: str, pos: int) -> int:
    newline = text.find("\n", pos)
    return len(text) if newline < 0 else newline + 1


def _line_start(text: str, pos: int) -> int:
    return text.rfind("\n", 0, pos) + 1


def _span(text: str, node: ast.stmt | ast.expr | ast.alias) -> tuple[int, int]:
    end_line = node.end_lineno or node.lineno
    return char_offset(text, node.lineno, node.col_offset), char_offset(text, end_line, node.end_col_offset or 0)


def _named(aliases: list[ast.alias]) -> str:
    return ", ".join(f"{a.name} as {a.asname}" if a.asname else a.name for a in aliases)


def _is_docstring(node: ast.stmt) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def leading_block_end(source: str) -> int:
    """After the leading run of imports; without one, after the module docstring."""
    body = ast.parse(source).body
    end = 0
    index = 0
    if body and _is_docstring(body[0]):
        end = _after_line(source, _span(source, body[0])[1])
        index = 1
    while index < len(body) and isinstance(body[index], (ast.Import, ast.ImportFrom)):
        end = _after_line(source, _span(source, body[index])[1])
        index += 1
    return end


class _Binding:
    """A name bound in a scope; `obj` is what an import binds it to, `plain` the module of an unaliased `import`."""

    def __init__(
        self, line: int, obj: str | None = None, plain: str | None = None,
        stmt: ast.Import | ast.ImportFrom | None = None, item: int = 0,
    ) -> None:
        self.line = line
        self.obj = obj
        self.plain = plain
        self.stmt = stmt
        self.item = item
        self.removed = False


class _Scope:
    def __init__(self, parent: _Scope | None, is_class: bool) -> None:
        self.parent = parent
        self.is_class = is_class
        self.bindings: dict[str, list[_Binding]] = {}
        self.stars: list[tuple[ast.ImportFrom, str | None]] = []

    def chain(self) -> Iterator[_Scope]:
        yield self
        scope = self.parent
        while scope is not None:
            if not scope.is_class:
                yield scope
            scope = scope.parent

    def lookup(self, name: str) -> _Scope | None:
        return next((scope for scope in self.chain() if name in scope.bindings), None)


class _Scopes:
    """Every binding per scope, every import with its scope, and every loaded name with the scope it is read in."""

    def __init__(self, tree: ast.Module, package: str) -> None:
        self.package = package
        self.module = _Scope(None, False)
        self.current = self.module
        self.imports: list[tuple[ast.Import | ast.ImportFrom, _Scope]] = []
        self.loads: dict[tuple[int, int], tuple[ast.Name, _Scope]] = {}
        self.visit(tree)

    def visit(self, node: ast.AST) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._function_def(node)
        elif isinstance(node, ast.Lambda):
            self._function(node, [node.body])
        elif isinstance(node, ast.ClassDef):
            self._class_def(node)
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            self._comprehension(node)
        elif isinstance(node, ast.Import):
            self._import(node)
        elif isinstance(node, ast.ImportFrom):
            self._import_from(node)
        elif isinstance(node, ast.Name):
            self._name(node)
        else:
            self._bind_pattern(node)
            self.generic_visit(node)

    def generic_visit(self, node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            self.visit(child)

    def _bind(self, name: str, binding: _Binding, scope: _Scope | None = None) -> None:
        (scope or self.current).bindings.setdefault(name, []).append(binding)

    def _inside(self, scope: _Scope, nodes: list) -> None:
        outer, self.current = self.current, scope
        for node in nodes:
            self.visit(node)
        self.current = outer

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda, body: list) -> None:
        args = node.args
        for default in [*args.defaults, *(d for d in args.kw_defaults if d is not None)]:
            self.visit(default)
        scope = _Scope(self.current, False)
        for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]:
            if arg is not None:
                self._bind(arg.arg, _Binding(arg.lineno), scope)
                if arg.annotation is not None:
                    self.visit(arg.annotation)
        self._inside(scope, body)

    def _function_def(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._bind(node.name, _Binding(node.lineno))
        for decorator in node.decorator_list:
            self.visit(decorator)
        if node.returns is not None:
            self.visit(node.returns)
        self._function(node, node.body)

    def _class_def(self, node: ast.ClassDef) -> None:
        self._bind(node.name, _Binding(node.lineno))
        for child in [*node.decorator_list, *node.bases, *node.keywords]:
            self.visit(child)
        self._inside(_Scope(self.current, True), node.body)

    def _comprehension(self, node: ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp) -> None:
        elements = [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]
        self._inside(_Scope(self.current, False), [*node.generators, *elements])

    def _import(self, node: ast.Import) -> None:
        self.imports.append((node, self.current))
        for index, alias in enumerate(node.names):
            if alias.asname:
                self._bind(alias.asname, _Binding(node.lineno, alias.name, None, node, index))
            else:
                root = alias.name.split(".")[0]
                self._bind(root, _Binding(node.lineno, root, alias.name, node, index))

    def _import_from(self, node: ast.ImportFrom) -> None:
        self.imports.append((node, self.current))
        base = _absolute(node.level, node.module or "", self.package)
        for index, alias in enumerate(node.names):
            if alias.name == "*":
                self.current.stars.append((node, base))
            else:
                obj = f"{base}.{alias.name}" if base else None
                self._bind(alias.asname or alias.name, _Binding(node.lineno, obj, None, node, index))

    def _name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.loads[(node.lineno, node.col_offset)] = (node, self.current)
        else:
            self._bind(node.id, _Binding(node.lineno))

    def _bind_pattern(self, node: ast.AST) -> None:
        """The name an `except ... as` clause or a match capture pattern binds."""
        if isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)):
            name = node.name
        elif isinstance(node, ast.MatchMapping):
            name = node.rest
        else:
            return
        if name:
            self._bind(name, _Binding(node.lineno))


class _Edits:
    def __init__(self, text: str) -> None:
        self.text = text
        self._pending: list[tuple[int, int, int, str]] = []

    def add(self, start: int, end: int, new: str) -> None:
        if not any(e[0] == start and e[1] == end and e[3] == new for e in self._pending):
            self._pending.append((start, end, len(self._pending), new))

    def insert_line(self, pos: int, line: str) -> None:
        """`line` as its own line at line start `pos`, keeping a missing final newline missing."""
        if pos == len(self.text) and self.text and not self.text.endswith("\n"):
            self.add(pos, pos, "\n" + line)
        else:
            self.add(pos, pos, line + "\n")

    def apply(self) -> str:
        out: list[str] = []
        cursor = 0
        for start, end, _, new in sorted(self._pending):
            if start < cursor:
                raise AssertionError(f"overlapping edits at {start}")
            out.append(self.text[cursor:start] + new)
            cursor = end
        return "".join(out) + self.text[cursor:]


class _File:
    """One module's source, scopes and pending edits."""

    def __init__(self, resource: File, package: str) -> None:
        self.resource = resource
        self.text = resource.read()
        self.tree = ast.parse(self.text)
        self.package = package
        self.scopes = _Scopes(self.tree, package)
        self.edits = _Edits(self.text)
        self.rewritten: set[int] = set()
        self.uses_rewritten: dict[int, int] = {}
        self.needs: list[tuple[str, _Binding | None, _Scope]] = []
        self.after: list[tuple[ast.stmt, str]] = []
        self.drops: dict[int, tuple[ast.Import | ast.ImportFrom, set[int]]] = {}

    def span(self, node: ast.stmt | ast.expr | ast.alias) -> tuple[int, int]:
        return _span(self.text, node)

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

    def binding_of(self, stmt: ast.Import | ast.ImportFrom, item: int, scope: _Scope) -> _Binding | None:
        alias = stmt.names[item]
        name = alias.asname or (alias.name.split(".")[0] if isinstance(stmt, ast.Import) else alias.name)
        return next((b for b in scope.bindings.get(name, []) if b.stmt is stmt and b.item == item), None)

    def rewrite_module(self, stmt: ast.ImportFrom, new: str) -> None:
        tokens = self.tokens(stmt)
        cut = next(i for i, tok in enumerate(tokens) if i and tok[0] == "import")
        if not new:
            start, end = self.span(stmt)
            comments = "".join(f"  {c}" for c in self.comments(stmt))
            self.edits.add(start, end, f"import {_named(stmt.names)}{comments}")
            return
        self.edits.add(tokens[1][1], tokens[cut - 1][2], new)

    def rewrite_dotted(self, stmt: ast.Import, item: int, new: str) -> None:
        start, end = self.span(stmt.names[item])
        name_end = start
        for text, tok_start, tok_end in self.tokens(stmt):
            if start <= tok_start < end:
                if text == "as":
                    break
                name_end = tok_end
        self.edits.add(start, name_end, new)

    def remove_item(self, stmt: ast.Import | ast.ImportFrom, item: int) -> None:
        self.drops.setdefault(id(stmt), (stmt, set()))[1].add(item)

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
            line_start, line_end = _line_start(self.text, start), _after_line(self.text, end)
            if bracketed and not self.text[line_start:start].strip() and _ITEM_TAIL.fullmatch(self.text[end:line_end]):
                self.edits.add(line_start, line_end, "")
            elif first:
                self.edits.add(spans[first - 1][1], end, "")
            elif last + 1 < len(spans):
                self.edits.add(start, spans[last + 1][0], "")
            else:
                comma = re.match(r"[ \t]*,", self.text[end:])
                self.edits.add(start, end + (comma.end() if comma else 0), "")

    def remove_stmt(self, stmt: ast.stmt) -> None:
        start, end = self.span(stmt)
        line_start, line_end = _line_start(self.text, start), _after_line(self.text, end)
        before = self.text[line_start:start]
        if not before.strip() and _LINE_TAIL.fullmatch(self.text[end:line_end]):
            self.edits.add(line_start, line_end, "")
        elif before.rstrip().endswith(";"):
            self.edits.add(self.text.rindex(";", line_start, start), end, "")
        else:
            tail = re.match(r"[ \t]*;[ \t]*", self.text[end:])
            self.edits.add(start, end + (tail.end() if tail else 0), "")

    def insert_after(self, stmt: ast.stmt, line: str) -> None:
        start, end = self.span(stmt)
        indent = re.match(r"[ \t]*", self.text[_line_start(self.text, start) :])
        self.edits.insert_line(_after_line(self.text, end), (indent.group() if indent else "") + line)

    def use_at(self, offset: int) -> tuple[ast.Name, _Scope] | None:
        line = self.text.count("\n", 0, offset) + 1
        col = len(self.text[_line_start(self.text, offset) : offset].encode())
        return self.scopes.loads.get((line, col))

    def rewrite_use(
        self, occurrence: occurrences.Occurrence, new: str, needs: str | None, obj: str | None = None
    ) -> None:
        """Rule 3: the chain becomes `new`, its root free for `obj` (default: itself); `needs` is the module to import."""
        start, end = _primary_range(occurrence)
        if not _CHAIN.fullmatch(self.text[start:end]):
            return
        use = self.use_at(start)
        if use is None:
            return
        name, scope = use
        root = new.split(".")[0]
        self.check_free(root, obj or root, scope)
        found = scope.lookup(name.id)
        binding = None
        if found is not None:
            imports = [b for b in found.bindings[name.id] if b.stmt is not None]
            before = [b for b in imports if b.line <= name.lineno]
            binding = (before or imports or [None])[-1]
        self.edits.add(start, end, new)
        if binding is not None:
            self.uses_rewritten[id(binding)] = self.uses_rewritten.get(id(binding), 0) + 1
        if needs is not None:
            self.needs.append((needs, binding, found if binding is not None and found is not None else self.scopes.module))

    def _uses(self, name: str, scope: _Scope) -> int:
        return sum(1 for node, at in self.scopes.loads.values() if node.id == name and at.lookup(name) is scope)

    def bound(self, scope: _Scope) -> Iterator[tuple[str, _Binding]]:
        for name, bindings in scope.bindings.items():
            for binding in bindings:
                yield name, binding

    def _all_scopes(self) -> Iterator[_Scope]:
        seen: dict[int, _Scope] = {id(self.scopes.module): self.scopes.module}
        for _, scope in self.scopes.imports:
            seen.setdefault(id(scope), scope)
        return iter(seen.values())

    def finish(self) -> str:
        """Remove imports whose every use was rewritten, add the imports rewritten uses need, and apply."""
        for scope in self._all_scopes():
            for name, binding in self.bound(scope):
                self._drop_if_all_rewritten(name, binding, scope)
        self._add_needed_imports()
        for stmt, line in self.after:
            self.insert_after(stmt, line)
        for stmt, items in self.drops.values():
            self._remove_items(stmt, items)
        return self.edits.apply()

    def _drop_if_all_rewritten(self, name: str, binding: _Binding, scope: _Scope) -> None:
        count = self.uses_rewritten.get(id(binding), 0)
        stmt = binding.stmt
        if count and stmt is not None and id(stmt) not in self.rewritten and self._uses(name, scope) == count:
            binding.removed = True
            self.remove_item(stmt, binding.item)

    def _add_needed_imports(self) -> None:
        added: set[tuple[str, int]] = set()
        for module, binding, scope in self.needs:
            key = (module, id(binding.stmt) if binding is not None else 0)
            if key in added or self.binds_module(scope, module):
                continue
            added.add(key)
            self.check_free(module.split(".")[0], module.split(".")[0], scope)
            if binding is not None and binding.stmt is not None:
                self.insert_after(binding.stmt, f"import {module}")
            else:
                self.edits.insert_line(leading_block_end(self.text), f"import {module}")

    def binds_module(self, scope: _Scope, module: str) -> bool:
        root = module.split(".")[0]
        found = scope.lookup(root)
        if found is None:
            return False
        return any(
            not b.removed and b.plain is not None and (b.plain == module or b.plain.startswith(module + "."))
            for b in found.bindings[root]
        )

    def check_free(self, name: str, obj: str, scope: _Scope) -> None:
        """Refuse when `name` already resolves, from `scope`, to anything but `obj`."""
        found = scope.lookup(name)
        if found is None:
            return
        for binding in found.bindings[name]:
            if not binding.removed and binding.obj != obj:
                raise NameConflict(name, self.resource.path, binding.line)


def _package(resource: Resource) -> str:
    name = libutils.modname(resource)
    return name if resource.name == _INIT else name.rpartition(".")[0]


def _explicitly_binds(resource: Resource, name: str) -> bool:
    """Whether the module (a package: its `__init__`) binds `name` at module level, by import or assignment."""
    if isinstance(resource, Folder):
        if not resource.has_child(_INIT):
            return False
        resource = resource.get_child(_INIT)
    if not isinstance(resource, File):
        return False
    scopes = _Scopes(ast.parse(resource.read()), _package(resource))
    return name in scopes.module.bindings


def _primary_range(occurrence: occurrences.Occurrence) -> tuple[int, int]:
    return cast(tuple[int, int], occurrence.get_primary_range())


def _primary(occurrence: occurrences.Occurrence) -> pynames.PyName | None:
    return cast(tuple[pynames.PyName | None, object], occurrence.get_primary_and_pyname())[0]


def _module_object(occurrence: occurrences.Occurrence) -> Resource | None:
    primary = _primary(occurrence)
    if primary is None:
        return None
    obj = primary.get_object()
    if isinstance(obj, (pyobjects.PyModule, pyobjects.PyPackage)):
        return obj.get_resource()
    return None


def _from(stmt: ast.ImportFrom, package: str, target: str) -> str:
    """The module `stmt` names `target` by: in its own relative or absolute form."""
    return relative_module(package, target) if stmt.level else target


def _finder(project: Project, name: str, pyname: object) -> occurrences.Finder:
    return occurrences.create_finder(project, name, pyname, imports=False, keywords=False)


class _ModuleMove:
    """The paths of one `move-module` and the per-file rewrites of its imports and uses."""

    def __init__(self, project: Project, mover: MoveModule, dest: Resource) -> None:
        self.source = mover.source
        self.basename = mover.old_name
        self.old = libutils.modname(self.source)
        dest_name = libutils.modname(dest)
        self.new = f"{dest_name}.{self.basename}" if dest_name else self.basename
        self.new_parent = self.new.rpartition(".")[0]
        self.old_parent = self.old.rpartition(".")[0]
        self.finder = _finder(project, self.basename, mover.old_pyname)
        self.binds: dict[str, bool] = {}

    def mapped(self, name: str) -> str | None:
        return self.new + name[len(self.old) :] if name == self.old or name.startswith(self.old + ".") else None

    def moves(self, resource: Resource) -> bool:
        return resource == self.source or resource.path.startswith(self.source.path + "/")

    def new_package(self, resource: Resource) -> str:
        name = libutils.modname(resource)
        new_name = self.mapped(name) or name
        return new_name if resource.name == _INIT else new_name.rpartition(".")[0]

    def rewrite_import(self, file: _File, stmt: ast.Import, scope: _Scope) -> None:
        for index, alias in enumerate(stmt.names):
            target = self.mapped(alias.name)
            if target is None:
                continue
            file.rewrite_dotted(stmt, index, target)
            file.rewritten.add(id(stmt))
            binding = file.binding_of(stmt, index, scope)
            if binding is not None and binding.plain is not None:
                binding.plain = target

    def rewrite_from(self, file: _File, stmt: ast.ImportFrom, moved: bool, package: str) -> None:
        base = _absolute(stmt.level, stmt.module or "", file.package)
        if base is None:
            return
        current = "." * stmt.level + (stmt.module or "")
        relocated = moved and stmt.level > 0
        target = self.mapped(base)
        hits = self._hits(stmt, base)
        if target is not None:
            if not relocated and _from(stmt, package, target) != current:
                file.rewrite_module(stmt, _from(stmt, package, target))
                file.rewritten.add(id(stmt))
            return
        if hits and len(hits) == len(stmt.names):
            file.rewrite_module(stmt, _from(stmt, package, self.new_parent) if self.new_parent else "")
            file.rewritten.add(id(stmt))
            return
        if hits:
            self._split(file, stmt, hits, package)
        if relocated and _from(stmt, package, base) != current:
            file.rewrite_module(stmt, _from(stmt, package, base))

    def _hits(self, stmt: ast.ImportFrom, base: str) -> list[int]:
        if base != self.old_parent:
            return []
        return [i for i, alias in enumerate(stmt.names) if alias.name == self.basename]

    def _split(self, file: _File, stmt: ast.ImportFrom, hits: list[int], package: str) -> None:
        for hit in hits:
            file.remove_item(stmt, hit)
        named = _named([stmt.names[i] for i in hits])
        line = f"from {_from(stmt, package, self.new_parent)} import {named}" if self.new_parent else f"import {named}"
        file.after.append((stmt, line))

    def rewrite_uses(self, file: _File) -> None:
        for occurrence in self.finder.find_occurrences(resource=file.resource):
            holder = _module_object(occurrence)
            if holder is None:
                continue
            if holder.path not in self.binds:
                self.binds[holder.path] = _explicitly_binds(holder, self.basename)
            if not self.binds[holder.path]:
                file.rewrite_use(occurrence, self.new, self.new)


def module_move_changes(project: Project, mover: MoveModule, dest: Resource) -> ChangeSet:
    """`move-module`: each import of the module rewritten in place, each broken use rewritten, then the move."""
    move = _ModuleMove(project, mover, dest)
    changes = ChangeSet(f"Moving module <{move.basename}>")
    for resource in project.get_python_files():
        moved = move.moves(resource)
        text = resource.read()
        if not moved and move.basename not in text:
            continue
        file = _File(resource, _package(resource))
        package = move.new_package(resource) if moved else file.package
        for stmt, scope in file.scopes.imports:
            if isinstance(stmt, ast.Import):
                move.rewrite_import(file, stmt, scope)
            else:
                move.rewrite_from(file, stmt, moved, package)
        move.rewrite_uses(file)
        result = file.finish()
        if result != text:
            changes.add_change(ChangeContents(resource, result))
    changes.add_change(MoveResource(move.source, dest.path))
    return changes


def _all_lists(tree: ast.Module) -> Iterator[list[ast.expr]]:
    for stmt in tree.body:
        if (
            isinstance(stmt, ast.Assign)
            and isinstance(stmt.value, (ast.List, ast.Tuple))
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in stmt.targets)
        ):
            yield stmt.value.elts


def _all_entry(file: _File, name: str) -> None:
    for elements in _all_lists(file.tree):
        index = next((i for i, e in enumerate(elements) if isinstance(e, ast.Constant) and e.value == name), None)
        if index is None:
            continue
        file.remove_elements([file.span(e) for e in elements], {index}, True)
        return


def _import_lines(info: ImportInfo, keep: list[tuple[str, str | None]]) -> str:
    named = [f"{name} as {alias}" if alias else name for name, alias in keep]
    if isinstance(info, FromImport):
        return f"from {info.module_name} import {', '.join(named)}"
    return "\n".join(f"import {n}" for n in named)


class _SymbolMove:
    """The paths of one `move-symbol` and the per-file edits of its references."""

    def __init__(self, project: Project, mover: MoveGlobal, dest: File) -> None:
        self.mover = mover
        self.source = mover.source
        self.dest = dest
        self.name = mover.old_name
        self.old = libutils.modname(self.source)
        self.new = libutils.modname(dest)
        self.region = cast(tuple[int, int], mover._get_moving_region())
        self.finder = _finder(project, self.name, mover.old_pyname)

    def edit(self, file: _File) -> None:
        is_dest = file.resource == self.dest
        _symbol_imports(file, self.old, self.new, self.name, is_dest)
        if file.resource == self.source:
            remaining = any(self._outside(o) for o in self.finder.find_occurrences(resource=file.resource))
            _source_edits(file, self.region, self.name, self.new, remaining)
        else:
            self._rewrite_uses(file, is_dest)
        if is_dest:
            _dest_edits(file, self.mover, self.old, self.new, self.name)

    def _outside(self, occurrence: occurrences.Occurrence) -> bool:
        start = _primary_range(occurrence)[0]
        return not (self.region[0] <= start < self.region[1] or occurrence.is_defined())

    def _rewrite_uses(self, file: _File, is_dest: bool) -> None:
        stars: list[ast.ImportFrom] = []
        for occurrence in self.finder.find_occurrences(resource=file.resource):
            if _module_object(occurrence) == self.source:
                if is_dest:
                    file.rewrite_use(occurrence, self.name, None, f"{self.old}.{self.name}")
                else:
                    file.rewrite_use(occurrence, f"{self.new}.{self.name}", self.new)
            elif _primary(occurrence) is None and not is_dest:
                stars.extend(_star_imports(file, _primary_range(occurrence)[0], self.old))
        for stmt in dict.fromkeys(stars):
            file.after.append((stmt, f"from {_from(stmt, file.package, self.new)} import {self.name}"))


def symbol_move_changes(project: Project, mover: MoveGlobal, dest: File) -> ChangeSet:
    """`move-symbol`: the moved code, its imports, and each reference edited in place."""
    move = _SymbolMove(project, mover, dest)
    changes = ChangeSet(f"Moving global <{move.name}>")
    for resource in project.get_python_files():
        text = resource.read()
        if resource not in (move.source, dest) and move.name not in text:
            continue
        file = _File(resource, _package(resource))
        move.edit(file)
        result = file.finish()
        if result != text:
            changes.add_change(ChangeContents(resource, result))
    return changes


def _symbol_imports(file: _File, old: str, new: str, name: str, is_dest: bool) -> None:
    for stmt, scope in file.scopes.imports:
        if not isinstance(stmt, ast.ImportFrom) or _absolute(stmt.level, stmt.module or "", file.package) != old:
            continue
        hits = [i for i, alias in enumerate(stmt.names) if alias.name == name]
        if not hits:
            continue
        _move_items(file, stmt, hits, None if is_dest else _from(stmt, file.package, new))
        if is_dest:
            _unalias(file, stmt, hits, scope, f"{old}.{name}")


def _unalias(file: _File, stmt: ast.ImportFrom, hits: list[int], scope: _Scope, obj: str) -> None:
    """Destination: free the removed import's names; each use of an alias it bound becomes the symbol's name."""
    for hit in hits:
        binding = file.binding_of(stmt, hit, scope)
        if binding is not None:
            binding.removed = True
    name = obj.rpartition(".")[2]
    for alias in {a for i in hits if (a := stmt.names[i].asname) and a != name}:
        other = next((b for b in scope.bindings[alias] if b.stmt is not stmt or b.item not in hits), None)
        if other is not None:
            raise NameConflict(alias, file.resource.path, other.line)
        for node, at in file.scopes.loads.values():
            if node.id == alias and at.lookup(alias) is scope:
                file.check_free(name, obj, at)
                file.edits.add(*file.span(node), name)


def _move_items(file: _File, stmt: ast.ImportFrom, hits: list[int], target: str | None) -> None:
    """Point the `hits` items of `stmt` at `target`, or drop them when `target` is None."""
    if target is not None and len(hits) == len(stmt.names):
        file.rewrite_module(stmt, target)
    else:
        for hit in hits:
            file.remove_item(stmt, hit)
        if target is not None:
            file.after.append((stmt, f"from {target} import {_named([stmt.names[i] for i in hits])}"))
    file.rewritten.add(id(stmt))


def _star_imports(file: _File, offset: int, old: str) -> list[ast.ImportFrom]:
    use = file.use_at(offset)
    if use is None or use[1].lookup(use[0].id) is not None:
        return []
    return [stmt for scope in use[1].chain() for stmt, base in scope.stars if base == old]


def _source_edits(file: _File, region: tuple[int, int], name: str, new: str, remaining: bool) -> None:
    file.edits.add(region[0], region[1], "")
    if remaining:
        file.edits.insert_line(leading_block_end(file.text), f"from {new} import {name}")
    _all_entry(file, name)
    module = file.scopes.module
    for bound, binding in file.bound(module):
        if binding.stmt is None or id(binding.stmt) in file.rewritten:
            continue
        uses = [node for node, at in file.scopes.loads.values() if node.id == bound and at.lookup(bound) is module]
        inside = [node for node in uses if region[0] <= char_offset(file.text, node.lineno, node.col_offset) < region[1]]
        if inside and len(inside) == len(uses):
            file.remove_item(binding.stmt, binding.item)


def _dest_edits(file: _File, mover: MoveGlobal, old: str, new: str, name: str) -> None:
    module = file.scopes.module
    for binding in module.bindings.get(name, []):
        if binding.obj != f"{old}.{name}":
            raise NameConflict(name, file.resource.path, binding.line)
    moving, infos = mover._get_moving_element_with_imports()
    read = {node.id for node in ast.walk(ast.parse(moving)) if isinstance(node, ast.Name)}
    lines = [line for info in infos if not _from_module(info, new) for line in _needed_import(file, info, read)]
    block_end = leading_block_end(file.text)
    for line in lines:
        file.edits.insert_line(block_end, line)
    _insert_moving(file, moving, block_end if lines else None)


def _from_module(info: ImportInfo, module: str) -> bool:
    return isinstance(info, FromImport) and info.module_name == module


def _needed_import(file: _File, info: ImportInfo, read: set[str]) -> list[str]:
    """The import the moved code needs from `info`, minus names the destination already binds to the same object."""
    module = file.scopes.module
    keep: list[tuple[str, str | None]] = []
    for imported, alias in info.names_and_aliases:
        bound, obj = _import_binding(info, imported, alias)
        if bound not in read:
            continue
        live = any(not b.removed for b in module.bindings.get(bound, []))
        if live:
            file.check_free(bound, obj, module)
        if not live or _plain_unbound(file, info, imported, alias):
            keep.append((imported, alias))
    return [_import_lines(info, keep)] if keep else []


def _plain_unbound(file: _File, info: ImportInfo, imported: str, alias: str | None) -> bool:
    """An unaliased `import a.b` whose root the destination binds, but not `a.b` itself."""
    return not alias and not isinstance(info, FromImport) and not file.binds_module(file.scopes.module, imported)


def _import_binding(info: ImportInfo, imported: str, alias: str | None) -> tuple[str, str]:
    """The name an import binds and the object it binds it to."""
    if isinstance(info, FromImport):
        return alias or imported, f"{info.module_name}.{imported}"
    bound = alias or imported.split(".")[0]
    return bound, imported if alias else bound


def _insert_moving(file: _File, moving: str, block_end: int | None) -> None:
    """Rope's position: after the last top-level import (or added import), else after the leading comments."""
    tops = [stmt for stmt in file.tree.body if isinstance(stmt, (ast.Import, ast.ImportFrom))]
    if tops or block_end is not None:
        at = max(_after_line(file.text, file.span(tops[-1])[1]) if tops else 0, block_end or 0)
        file.edits.add(at, at, "\n\n" + moving)
        return
    comments = 0
    source_lines = file.text.split("\n")
    while comments < len(source_lines) - 1 and source_lines[comments].lstrip().startswith("#"):
        comments += 1
    at = sum(len(line) + 1 for line in source_lines[:comments])
    file.edits.add(at, at, ("\n\n" if comments else "") + moving)
