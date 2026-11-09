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
_ITEM_TAIL = re.compile(r"[ \t]*,?[ \t]*(?:#[^\n]*)?\n?")
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
        handler = getattr(self, f"visit_{type(node).__name__}", None)
        if handler is not None:
            handler(node)
        else:
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

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._bind(node.name, _Binding(node.lineno))
        for decorator in node.decorator_list:
            self.visit(decorator)
        if node.returns is not None:
            self.visit(node.returns)
        self._function(node, node.body)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._function(node, [node.body])

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._bind(node.name, _Binding(node.lineno))
        for child in [*node.decorator_list, *node.bases, *node.keywords]:
            self.visit(child)
        self._inside(_Scope(self.current, True), node.body)

    def _comprehension(self, node: ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp) -> None:
        elements = [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]
        self._inside(_Scope(self.current, False), [*node.generators, *elements])

    visit_ListComp = visit_SetComp = visit_GeneratorExp = visit_DictComp = _comprehension

    def visit_Import(self, node: ast.Import) -> None:
        self.imports.append((node, self.current))
        for index, alias in enumerate(node.names):
            if alias.asname:
                self._bind(alias.asname, _Binding(node.lineno, alias.name, None, node, index))
            else:
                root = alias.name.split(".")[0]
                self._bind(root, _Binding(node.lineno, root, alias.name, node, index))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.imports.append((node, self.current))
        base = _absolute(node.level, node.module or "", self.package)
        for index, alias in enumerate(node.names):
            if alias.name == "*":
                self.current.stars.append((node, base))
            else:
                obj = f"{base}.{alias.name}" if base else None
                self._bind(alias.asname or alias.name, _Binding(node.lineno, obj, None, node, index))

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.loads[(node.lineno, node.col_offset)] = (node, self.current)
        else:
            self._bind(node.id, _Binding(node.lineno))

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self._bind(node.name, _Binding(node.lineno))
        self.generic_visit(node)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name:
            self._bind(node.name, _Binding(node.lineno))
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name:
            self._bind(node.name, _Binding(node.lineno))

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest:
            self._bind(node.rest, _Binding(node.lineno))
        self.generic_visit(node)


class _Edits:
    def __init__(self, text: str) -> None:
        self.text = text
        self._edits: list[tuple[int, int, int, str]] = []

    def add(self, start: int, end: int, new: str) -> None:
        if not any(e[0] == start and e[1] == end and e[3] == new for e in self._edits):
            self._edits.append((start, end, len(self._edits), new))

    def insert_line(self, pos: int, line: str) -> None:
        """`line` as its own line at line start `pos`, keeping a missing final newline missing."""
        if pos == len(self.text) and self.text and not self.text.endswith("\n"):
            self.add(pos, pos, "\n" + line)
        else:
            self.add(pos, pos, line + "\n")

    def apply(self) -> str:
        out: list[str] = []
        cursor = 0
        for start, end, _, new in sorted(self._edits):
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

    def binding_of(self, stmt: ast.Import | ast.ImportFrom, item: int, scope: _Scope) -> _Binding | None:
        alias = stmt.names[item]
        name = alias.asname or (alias.name.split(".")[0] if isinstance(stmt, ast.Import) else alias.name)
        return next((b for b in scope.bindings.get(name, []) if b.stmt is stmt and b.item == item), None)

    def rewrite_module(self, stmt: ast.ImportFrom, new: str) -> None:
        tokens = self.tokens(stmt)
        cut = next(i for i, tok in enumerate(tokens) if i and tok[0] == "import")
        if not new:
            alias = stmt.names[0]
            start, end = self.span(stmt)
            self.edits.add(start, end, f"import {alias.name}" + (f" as {alias.asname}" if alias.asname else ""))
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
            else:
                self.edits.add(start, spans[last + 1][0], "")

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

    def rewrite_use(self, occurrence: occurrences.Occurrence, new: str, needs: str | None) -> None:
        """Rule 3: the chain becomes `new`; `needs` is the module an import must bind for it."""
        start, end = _primary_range(occurrence)
        if not _CHAIN.fullmatch(self.text[start:end]):
            return
        use = self.use_at(start)
        if use is None:
            return
        name, scope = use
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
                count = self.uses_rewritten.get(id(binding), 0)
                stmt = binding.stmt
                if count and stmt is not None and id(stmt) not in self.rewritten and self._uses(name, scope) == count:
                    binding.removed = True
                    self.remove_item(stmt, binding.item)
        added: set[tuple[str, int]] = set()
        for module, binding, scope in self.needs:
            key = (module, id(binding.stmt) if binding is not None else 0)
            if key in added or self._binds_module(scope, module):
                continue
            added.add(key)
            self.check_free(module.split(".")[0], module.split(".")[0], scope)
            if binding is not None and binding.stmt is not None:
                self.insert_after(binding.stmt, f"import {module}")
            else:
                self.edits.insert_line(leading_block_end(self.text), f"import {module}")
        for stmt, line in self.after:
            self.insert_after(stmt, line)
        for stmt, items in self.drops.values():
            self._remove_items(stmt, items)
        return self.edits.apply()

    def _binds_module(self, scope: _Scope, module: str) -> bool:
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
    return name if resource.name == "__init__.py" else name.rpartition(".")[0]


def _explicitly_binds(resource: Resource, name: str) -> bool:
    """Whether the module (a package: its `__init__`) binds `name` at module level, by import or assignment."""
    if isinstance(resource, Folder):
        if not resource.has_child("__init__.py"):
            return False
        resource = resource.get_child("__init__.py")
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


def module_move_changes(project: Project, mover: MoveModule, dest: Resource) -> ChangeSet:
    """`move-module`: each import of the module rewritten in place, each broken use rewritten, then the move."""
    source = mover.source
    basename = mover.old_name
    old = libutils.modname(source)
    dest_name = libutils.modname(dest)
    new = f"{dest_name}.{basename}" if dest_name else basename
    new_parent = new.rpartition(".")[0]
    old_parent = old.rpartition(".")[0]
    prefix = source.path + "/"

    def mapped(name: str) -> str | None:
        return new + name[len(old) :] if name == old or name.startswith(old + ".") else None

    finder = _finder(project, basename, mover.old_pyname)
    binds: dict[str, bool] = {}
    changes = ChangeSet(f"Moving module <{basename}>")
    for resource in project.get_python_files():
        moved = resource == source or resource.path.startswith(prefix)
        text = resource.read()
        if not moved and basename not in text:
            continue
        old_package = _package(resource)
        new_package = old_package
        if moved:
            new_name = mapped(libutils.modname(resource)) or libutils.modname(resource)
            new_package = new_name if resource.name == "__init__.py" else new_name.rpartition(".")[0]
        file = _File(resource, old_package)
        for stmt, scope in file.scopes.imports:
            if isinstance(stmt, ast.Import):
                for index, alias in enumerate(stmt.names):
                    target = mapped(alias.name)
                    if target is not None:
                        file.rewrite_dotted(stmt, index, target)
                        file.rewritten.add(id(stmt))
                        binding = file.binding_of(stmt, index, scope)
                        if binding is not None and binding.plain is not None:
                            binding.plain = target
                continue
            base = _absolute(stmt.level, stmt.module or "", old_package)
            if base is None:
                continue
            current = "." * stmt.level + (stmt.module or "")
            target = mapped(base)
            hits = [i for i, alias in enumerate(stmt.names) if base == old_parent and alias.name == basename]
            if target is not None:
                if not (moved and stmt.level) and _from(stmt, new_package, target) != current:
                    file.rewrite_module(stmt, _from(stmt, new_package, target))
                    file.rewritten.add(id(stmt))
            elif hits and len(stmt.names) == 1:
                file.rewrite_module(stmt, _from(stmt, new_package, new_parent) if new_parent else "")
                file.rewritten.add(id(stmt))
            else:
                if hits:
                    alias = stmt.names[hits[0]]
                    file.remove_item(stmt, hits[0])
                    named = f"{alias.name} as {alias.asname}" if alias.asname else alias.name
                    file.after.append(
                        (stmt, f"from {_from(stmt, new_package, new_parent)} import {named}" if new_parent else f"import {named}")
                    )
                if moved and stmt.level and _from(stmt, new_package, base) != current:
                    file.rewrite_module(stmt, _from(stmt, new_package, base))
        for occurrence in finder.find_occurrences(resource=resource):
            holder = _module_object(occurrence)
            if holder is None:
                continue
            if holder.path not in binds:
                binds[holder.path] = _explicitly_binds(holder, basename)
            if not binds[holder.path]:
                file.rewrite_use(occurrence, new, new)
        result = file.finish()
        if result != text:
            changes.add_change(ChangeContents(resource, result))
    changes.add_change(MoveResource(source, dest.path))
    return changes


def _all_entry(file: _File, name: str) -> None:
    for stmt in file.tree.body:
        if not (isinstance(stmt, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in stmt.targets)):
            continue
        if not isinstance(stmt.value, (ast.List, ast.Tuple)):
            continue
        elements = stmt.value.elts
        for index, element in enumerate(elements):
            if isinstance(element, ast.Constant) and element.value == name:
                if len(elements) == 1:
                    file.edits.add(*file.span(element), "")
                else:
                    file.remove_elements([file.span(e) for e in elements], {index}, True)
                return


def _import_lines(info: ImportInfo, keep: list[tuple[str, str | None]]) -> str:
    named = [f"{name} as {alias}" if alias else name for name, alias in keep]
    if isinstance(info, FromImport):
        return f"from {info.module_name} import {', '.join(named)}"
    return "\n".join(f"import {n}" for n in named)


def symbol_move_changes(project: Project, mover: MoveGlobal, dest: File) -> ChangeSet:
    """`move-symbol`: the moved code, its imports, and each reference edited in place."""
    source = mover.source
    name = mover.old_name
    old = libutils.modname(source)
    new = libutils.modname(dest)
    region_start, region_end = mover._get_moving_region()
    finder = _finder(project, name, mover.old_pyname)
    changes = ChangeSet(f"Moving global <{name}>")
    for resource in project.get_python_files():
        text = resource.read()
        if resource not in (source, dest) and name not in text:
            continue
        package = _package(resource)
        file = _File(resource, package)
        _symbol_imports(file, old, new, name, resource == dest)
        stars: list[ast.ImportFrom] = []
        remaining = False
        for occurrence in finder.find_occurrences(resource=resource):
            start = _primary_range(occurrence)[0]
            if resource == source:
                remaining = remaining or not (region_start <= start < region_end or occurrence.is_defined())
                continue
            if _module_object(occurrence) == source:
                file.rewrite_use(occurrence, name if resource == dest else f"{new}.{name}", None if resource == dest else new)
            elif _primary(occurrence) is None and resource != dest:
                stars.extend(_star_imports(file, start, old))
        for stmt in dict.fromkeys(stars):
            file.after.append((stmt, f"from {_from(stmt, package, new)} import {name}"))
        if resource == source:
            _source_edits(file, (region_start, region_end), name, new, remaining)
        if resource == dest:
            _dest_edits(file, mover, old, new, name)
        result = file.finish()
        if result != text:
            changes.add_change(ChangeContents(resource, result))
    return changes


def _symbol_imports(file: _File, old: str, new: str, name: str, is_dest: bool) -> None:
    for stmt, _ in file.scopes.imports:
        if not isinstance(stmt, ast.ImportFrom) or _absolute(stmt.level, stmt.module or "", file.package) != old:
            continue
        hits = [i for i, alias in enumerate(stmt.names) if alias.name == name]
        if not hits:
            continue
        target = _from(stmt, file.package, new)
        if is_dest:
            file.remove_item(stmt, hits[0])
        elif len(stmt.names) == 1:
            file.rewrite_module(stmt, target)
        else:
            alias = stmt.names[hits[0]]
            file.remove_item(stmt, hits[0])
            file.after.append((stmt, f"from {target} import {alias.name}" + (f" as {alias.asname}" if alias.asname else "")))
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
    lines: list[str] = []
    for info in infos:
        if isinstance(info, FromImport) and info.module_name == new:
            continue
        keep: list[tuple[str, str | None]] = []
        for imported, alias in info.names_and_aliases:
            if isinstance(info, FromImport):
                bound, obj = alias or imported, f"{info.module_name}.{imported}"
            else:
                bound = alias or imported.split(".")[0]
                obj = imported if alias else bound
            if bound not in read:
                continue
            if bound in module.bindings:
                file.check_free(bound, obj, module)
            else:
                keep.append((imported, alias))
        if keep:
            lines.append(_import_lines(info, keep))
    block_end = leading_block_end(file.text)
    for line in lines:
        file.edits.insert_line(block_end, line)
    tops = [stmt for stmt in file.tree.body if isinstance(stmt, (ast.Import, ast.ImportFrom))]
    if tops or lines:
        at = max(_after_line(file.text, file.span(tops[-1])[1]) if tops else 0, block_end if lines else 0)
        file.edits.add(at, at, "\n\n" + moving)
        return
    comments = 0
    source_lines = file.text.split("\n")
    while comments < len(source_lines) - 1 and source_lines[comments].lstrip().startswith("#"):
        comments += 1
    at = sum(len(line) + 1 for line in source_lines[:comments])
    file.edits.add(at, at, ("\n\n" if comments else "") + moving)
