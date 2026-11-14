"""`explicit-any`: every reference that resolves to `typing.Any`, by static analysis of the source alone."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from living_architecture.contract import language, message

TYPING_MODULES = frozenset({"typing", "typing_extensions"})
_TYPE_COMMENT = re.compile(r"#\s*type:\s*(.*)")
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)

ScopeKind = Literal["module", "class", "function", "comprehension"]
# ("typing", member) is a member of typing / typing_extensions; ("module", dotted) a module; None anything else.
Value = tuple[Literal["typing", "module"], str] | None
# ("module", dotted, "") is `import`, ("member", module, name) `from module import name`; None any other binding.
Binding = tuple[Literal["module", "member"], str | None, str] | None
ANY: Value = ("typing", "Any")


def _combine(values: list[Value]) -> Value:
    """The one value every binding agrees on, else None."""
    first = values[0] if values else None
    return first if first is not None and all(v == first for v in values) else None


class _Scope:
    def __init__(self, kind: ScopeKind, parent: _Scope | None) -> None:
        self.kind: ScopeKind = kind
        self.parent = parent
        self.module: _Scope = parent.module if parent is not None else self
        self.raw: defaultdict[str, list[Binding]] = defaultdict(list)
        self.bindings: defaultdict[str, list[Binding]] = defaultdict(list)
        self.globals: set[str] = set()
        self.nonlocals: set[str] = set()

    def _enclosing(self) -> Iterator[_Scope]:
        """The enclosing function scopes, innermost first; class scopes are skipped."""
        scope = self.parent
        while scope is not None and scope.kind != "module":
            if scope.kind != "class":
                yield scope
            scope = scope.parent

    def owner(self, name: str) -> _Scope:
        """The scope a binding of `name` here binds in."""
        if name in self.globals:
            return self.module
        if name in self.nonlocals:
            for scope in self._enclosing():
                if name in scope.raw or name in scope.nonlocals:
                    return scope.owner(name)
            return self.module
        return self

    def resolving(self, name: str) -> _Scope:
        """The scope that resolves a use of `name` here."""
        if name in self.globals or name in self.nonlocals:
            return self.owner(name)
        if self.kind == "module" or name in self.bindings:
            return self
        for scope in self._enclosing():
            if name in scope.globals or name in scope.nonlocals:
                return scope.owner(name)
            if name in scope.bindings:
                return scope
        return self.module


class _CommentRoot:
    def __init__(self, node: ast.AST, text: str, scope: _Scope, signature: bool) -> None:
        self.node, self.text, self.scope, self.signature = node, text, scope, signature
        self.position: tuple[int, int] = (getattr(node, "lineno", 0), getattr(node, "col_offset", 0))


class _Binder:
    """Scopes and bindings of a module, its name and attribute loads, and its type expressions for later reading."""

    def __init__(self, parts: list[str], is_package: bool) -> None:
        self.parts, self.is_package = parts, is_package
        self.module = _Scope("module", None)
        self.scopes = [self.module]
        self.stars: list[str | None] = []
        self.loads: list[tuple[ast.expr, _Scope]] = []
        self.annotations: list[tuple[ast.expr, _Scope]] = []
        self.comments: list[_CommentRoot] = []

    def _new(self, kind: ScopeKind, parent: _Scope) -> _Scope:
        scope = _Scope(kind, parent)
        self.scopes.append(scope)
        return scope

    def _from_module(self, node: ast.ImportFrom) -> str | None:
        if node.level == 0:
            return node.module
        package = self.parts if self.is_package else self.parts[:-1]
        if node.level - 1 >= len(package):
            return None
        return ".".join(package[: len(package) - node.level + 1] + ([node.module] if node.module else []))

    def _comment(self, node: ast.AST, text: str | None, scope: _Scope, signature: bool = False) -> None:
        if text is not None:
            self.comments.append(_CommentRoot(node, text, scope, signature))

    def _signature(self, args: ast.arguments, scope: _Scope) -> list[ast.arg]:
        """`args`' defaults, annotations and type comments read in `scope`; the parameters."""
        params = [*args.posonlyargs, *args.args, args.vararg, *args.kwonlyargs, args.kwarg]
        for default in [*args.defaults, *args.kw_defaults]:
            if default is not None:
                self.visit(default, scope)
        present = [p for p in params if p is not None]
        for param in present:
            if param.annotation is not None:
                self.annotations.append((param.annotation, scope))
            self._comment(param, param.type_comment, scope)
        return present

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda, scope: _Scope) -> None:
        if not isinstance(node, ast.Lambda):
            for decorator in node.decorator_list:
                self.visit(decorator, scope)
            if node.returns is not None:
                self.annotations.append((node.returns, scope))
            self._comment(node, node.type_comment, scope, signature=True)
            scope.raw[node.name].append(None)
        inner = self._new("function", scope)
        for param in self._signature(node.args, scope):
            inner.raw[param.arg].append(None)
        for child in node.body if isinstance(node.body, list) else [node.body]:
            self.visit(child, inner)

    def _class(self, node: ast.ClassDef, scope: _Scope) -> None:
        for expr in [*node.decorator_list, *node.bases, *(k.value for k in node.keywords)]:
            self.visit(expr, scope)
        scope.raw[node.name].append(None)
        inner = self._new("class", scope)
        for stmt in node.body:
            self.visit(stmt, inner)

    def _comprehension(self, node: ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp, scope: _Scope) -> None:
        self.visit(node.generators[0].iter, scope)
        inner = self._new("comprehension", scope)
        for i, generator in enumerate(node.generators):
            if i:
                self.visit(generator.iter, inner)
            self.visit(generator.target, inner)
            for condition in generator.ifs:
                self.visit(condition, inner)
        for part in [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]:
            self.visit(part, inner)

    def _imports(self, node: ast.Import | ast.ImportFrom, scope: _Scope) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                scope.raw[name].append(("module", alias.name if alias.asname else name, ""))
            return
        module = self._from_module(node)
        for alias in node.names:
            if alias.name == "*":
                self.stars.append(module)
            else:
                scope.raw[alias.asname or alias.name].append(("member", module, alias.name))

    @staticmethod
    def _named_target(node: ast.AST) -> str | None:
        """The name an except handler or match pattern binds."""
        if isinstance(node, ast.ExceptHandler | ast.MatchAs | ast.MatchStar):
            return node.name
        if isinstance(node, ast.MatchMapping):
            return node.rest
        return None

    def visit(self, node: ast.AST, scope: _Scope) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            return self._function(node, scope)
        if isinstance(node, ast.ClassDef):
            return self._class(node, scope)
        if isinstance(node, _COMPREHENSIONS):
            return self._comprehension(node, scope)
        if isinstance(node, ast.Import | ast.ImportFrom):
            return self._imports(node, scope)
        if isinstance(node, ast.Global):
            scope.globals.update(node.names)
        elif isinstance(node, ast.Nonlocal):
            scope.nonlocals.update(node.names)
        elif isinstance(node, ast.NamedExpr):
            target = scope
            while target.kind == "comprehension" and target.parent is not None:
                target = target.parent
            target.raw[node.target.id].append(None)
            return self.visit(node.value, scope)
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                self.loads.append((node, scope))
            else:
                scope.raw[node.id].append(None)
            return None
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            self.loads.append((node, scope))
        elif isinstance(node, ast.AnnAssign):
            self.annotations.append((node.annotation, scope))
            for part in [node.target, node.value]:
                if part is not None:
                    self.visit(part, scope)
            return None
        elif isinstance(node, ast.Assign | ast.For | ast.AsyncFor | ast.With | ast.AsyncWith):
            self._comment(node, node.type_comment, scope)
        if (name := self._named_target(node)) is not None:
            scope.raw[name].append(None)
        for child in ast.iter_child_nodes(node):
            self.visit(child, scope)
        return None


def _literal_all(tree: ast.Module) -> set[str] | None:
    """The names of the module's last top-level `__all__` assignment when it is a literal of strings."""
    names: set[str] | None = None
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            targets, value = stmt.targets, stmt.value
        elif isinstance(stmt, ast.AnnAssign):
            targets, value = [stmt.target], stmt.value
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
            continue
        elts = value.elts if isinstance(value, ast.List | ast.Tuple) else None
        strings = [e.value for e in elts or [] if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        names = set(strings) if elts is not None and len(strings) == len(elts) else None
    return names


class _Module:
    def __init__(self, tree: ast.Module, parts: list[str], is_package: bool) -> None:
        self.dotted = ".".join(parts)
        binder = _Binder(parts, is_package)
        for stmt in tree.body:
            binder.visit(stmt, binder.module)
        for scope in binder.scopes:
            for name, found in scope.raw.items():
                scope.owner(name).bindings[name].extend(found)
        self.binder = binder
        self.scope = binder.module
        self.stars = binder.stars
        self.all_names = _literal_all(tree)


class _Resolver:
    """Resolves names and attributes to values, following first-party modules under `root`."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.modules: dict[str, _Module | None] = {}
        self.active: set[tuple[str, str]] = set()
        self.cache: dict[tuple[str, str], list[Value]] = {}

    def load(self, dotted: str) -> _Module | None:
        if dotted not in self.modules:
            self.modules[dotted] = self._parse(dotted)
        return self.modules[dotted]

    def _parse(self, dotted: str) -> _Module | None:
        parts = dotted.split(".")
        if not all(p.isidentifier() for p in parts):
            return None
        base = self.root.joinpath(*parts)
        for path, is_package in ((base / "__init__.py", True), (base.parent / f"{base.name}.py", False)):
            if path.is_file():
                try:
                    return _Module(ast.parse(path.read_text(encoding="utf-8")), parts, is_package)
                except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
                    return None
        return None

    def module_values(self, module: _Module, name: str) -> list[Value]:
        """The values of every module-level binding of `name`, star imports included."""
        key = (module.dotted, name)
        if key in self.cache:
            return self.cache[key]
        if key in self.active:
            return [None]
        top = not self.active
        self.active.add(key)
        try:
            values = [self.binding_value(b) for b in module.scope.bindings.get(name, [])]
            for star in module.stars:
                values += self.star_values(star, name)
        finally:
            self.active.discard(key)
        if top:
            self.cache[key] = values
        return values

    def binding_value(self, binding: Binding) -> Value:
        if binding is None:
            return None
        kind, module, name = binding
        if kind == "module":
            return ("module", module) if module is not None else None
        return self.member(module, name)

    def member(self, module: str | None, name: str) -> Value:
        """The value of `module.name`."""
        if module is None:
            return None
        if module in TYPING_MODULES:
            return ("typing", name)
        if (target := self.load(module)) is None:
            return None
        if values := self.module_values(target, name):
            return _combine(values)
        return ("module", f"{module}.{name}") if self.load(f"{module}.{name}") is not None else None

    def star_values(self, module: str | None, name: str) -> list[Value]:
        """What `from module import *` binds `name` to, if anything."""
        if module in TYPING_MODULES:
            return [ANY] if name == "Any" else []
        if module is None or (target := self.load(module)) is None:
            return []
        exported = name in target.all_names if target.all_names is not None else not name.startswith("_")
        return self.module_values(target, name) if exported else []

    def values(self, module: _Module, scope: _Scope, expr: ast.expr) -> list[Value]:
        """The values every binding behind `expr` gives it."""
        if isinstance(expr, ast.Name):
            owner = scope.resolving(expr.id)
            if owner.kind == "module":
                return self.module_values(module, expr.id)
            return [self.binding_value(b) for b in owner.bindings.get(expr.id, [])]
        if isinstance(expr, ast.Attribute):
            return [
                self.member(v[1], expr.attr) if v is not None and v[0] == "module" else None
                for v in self.values(module, scope, expr.value)
            ]
        return [None]

    def resolve(self, module: _Module, scope: _Scope, expr: ast.expr) -> Value:
        return _combine(self.values(module, scope, expr))


def _parse_expression(text: str, mode: Literal["eval", "func_type"] = "eval") -> ast.expr | ast.FunctionType | None:
    try:
        tree = ast.parse(text.strip(), mode=mode)
    except (SyntaxError, ValueError):
        return None
    if isinstance(tree, ast.Expression):
        return tree.body
    return tree if isinstance(tree, ast.FunctionType) else None


class _Reader:
    """The lines of a module's references to `Any`."""

    def __init__(self, resolver: _Resolver, module: _Module) -> None:
        self.resolver, self.module = resolver, module
        self.loads: list[tuple[ast.expr, _Scope, int]] = [(n, s, n.lineno) for n, s in module.binder.loads]

    def _plain(self, node: ast.AST, scope: _Scope, line: int | None) -> None:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name | ast.Attribute) and isinstance(sub.ctx, ast.Load):
                self.loads.append((sub, scope, line if line is not None else sub.lineno))

    def _head(self, node: ast.expr, scope: _Scope) -> str | None:
        value = self.resolver.resolve(self.module, scope, node)
        if value is not None and value[0] == "typing":
            return value[1]
        return node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None

    def type_expression(self, node: ast.AST, scope: _Scope, line: int | None, forward: bool = True) -> None:
        """Reads a type expression; a string is a forward reference where `forward` allows one."""
        if isinstance(node, ast.Constant):
            if forward and isinstance(node.value, str):
                parsed = _parse_expression(node.value)
                if isinstance(parsed, ast.expr):
                    self.type_expression(parsed, scope, line if line is not None else node.lineno)
            return
        if isinstance(node, ast.Subscript):
            self._plain(node.value, scope, line)
            head = self._head(node.value, scope)
            elements = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
            for i, element in enumerate(elements):
                if head == "Literal" or (head == "Annotated" and i > 0):
                    self._plain(element, scope, line)
                else:
                    self._element(element, scope, line)
            return
        if isinstance(node, ast.BinOp):
            for side in (node.left, node.right):
                self.type_expression(side, scope, line, forward=False)
            return
        self._plain(node, scope, line)

    def _element(self, node: ast.expr, scope: _Scope, line: int | None) -> None:
        if isinstance(node, ast.List):
            for element in node.elts:
                self._element(element, scope, line)
        else:
            self.type_expression(node, scope, line)

    def comment(self, root: _CommentRoot, line: int) -> None:
        parsed = _parse_expression(root.text, "func_type" if root.signature else "eval")
        if isinstance(parsed, ast.FunctionType):
            for part in [*parsed.argtypes, parsed.returns]:
                self.type_expression(part, root.scope, line)
        elif isinstance(parsed, ast.expr):
            self.type_expression(parsed, root.scope, line)

    def lines(self) -> list[int]:
        return sorted(line for node, scope, line in self.loads if self.resolver.resolve(self.module, scope, node) == ANY)


def _type_comment_tokens(text: str) -> list[tuple[int, int, str]]:
    """Each `# type:` comment's line, column and comment text."""
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, SyntaxError):
        return []
    comments = (t for t in tokens if t.type == tokenize.COMMENT and _TYPE_COMMENT.match(t.string))
    return [(t.start[0], t.start[1], t.string) for t in comments]


def _parse_typed(source: str) -> tuple[ast.Module, str]:
    """The tree with type comments, blanking each misplaced one; without them if the source still fails."""
    lines = source.splitlines(keepends=True)
    while True:
        text = "".join(lines)
        try:
            return ast.parse(text, type_comments=True), text
        except SyntaxError as exc:
            found = [(col, s) for line, col, s in _type_comment_tokens(text) if line == exc.lineno]
            if not found or exc.lineno is None:
                return ast.parse(source), source
            col, comment = found[0]
            row = lines[exc.lineno - 1]
            lines[exc.lineno - 1] = row[:col] + " " * len(comment) + row[col + len(comment) :]


def _comment_lines(roots: list[_CommentRoot], text: str) -> Iterator[tuple[_CommentRoot, int]]:
    """Each type comment with the line it is written on, matched in source order."""
    tokens = _type_comment_tokens(text)
    used: set[int] = set()
    for root in sorted(roots, key=lambda r: r.position):
        line = root.position[0]
        for i, (row, _, comment) in enumerate(tokens):
            match = _TYPE_COMMENT.match(comment)
            if i not in used and row >= line and match is not None and match.group(1).strip() == root.text.strip():
                used.add(i)
                line = row
                break
        yield root, line


def _location(path: Path) -> tuple[Path, list[str], bool]:
    """The file's import root (the parent of its topmost package), its module name parts, and whether a package."""
    root = path.parent
    while (root / "__init__.py").is_file():
        root = root.parent
    parts = list(path.relative_to(root).with_suffix("").parts)
    is_package = parts[-1] == "__init__"
    return root, parts[:-1] if is_package else parts, is_package


def check_explicit_any(path: Path, source: str) -> list[str]:
    """One `compliance.explicit-any` finding per reference to `Any` in a file that parses."""
    root, parts, is_package = _location(path.resolve())
    tree, text = _parse_typed(source)
    module = _Module(tree, parts, is_package)
    resolver = _Resolver(root)
    resolver.modules[module.dotted] = module
    reader = _Reader(resolver, module)
    for annotation, scope in module.binder.annotations:
        reader.type_expression(annotation, scope, None)
    for comment, line in _comment_lines(module.binder.comments, text):
        reader.comment(comment, line)
    facts = language("python")
    return [
        message("compliance.explicit-any", path=str(path), line=line, any=facts["any_type"], top=facts["top_type"])
        for line in reader.lines()
    ]
