"""`explicit-any`: every reference that resolves to `typing.Any`, by static analysis of the source alone."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

from living_architecture.contract import language, message
from living_architecture.refactor.static_resolver import (
    ANY,
    CommentRoot,
    Module,
    ModuleFinder,
    Resolver,
    Scope,
)

_TYPE_COMMENT = re.compile(r"#\s*type:\s*(.*)")


def _import_root_finder(root: Path) -> ModuleFinder:
    """Modules under `root`, the import root of the checked file."""

    def find(dotted: str) -> tuple[Path, bool] | None:
        base = root.joinpath(*dotted.split("."))
        for path, is_package in ((base / "__init__.py", True), (base.parent / f"{base.name}.py", False)):
            if path.is_file():
                return path, is_package
        return None

    return find


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

    def __init__(self, resolver: Resolver, module: Module) -> None:
        self.resolver, self.module = resolver, module
        self.loads: list[tuple[ast.expr, Scope, int]] = [(n, s, n.lineno) for n, s in module.binder.loads]

    def _plain(self, node: ast.AST, scope: Scope, line: int | None) -> None:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name | ast.Attribute) and isinstance(sub.ctx, ast.Load):
                self.loads.append((sub, scope, line if line is not None else sub.lineno))

    def _head(self, node: ast.expr, scope: Scope) -> str | None:
        value = self.resolver.resolve(self.module, scope, node)
        if value is not None and value[0] == "typing":
            return value[1]
        if isinstance(node, ast.Name):
            return node.id
        return node.attr if isinstance(node, ast.Attribute) else None

    def type_expression(self, node: ast.AST, scope: Scope, line: int | None, forward: bool = True) -> None:
        """Reads a type expression; a string is a forward reference where `forward` allows one."""
        if isinstance(node, ast.Constant):
            if forward and isinstance(node.value, str):
                self._forward(node.value, scope, line if line is not None else node.lineno)
        elif isinstance(node, ast.Subscript):
            self._subscript(node, scope, line)
        elif isinstance(node, ast.BinOp):
            for side in (node.left, node.right):
                self.type_expression(side, scope, line, forward=False)
        else:
            self._plain(node, scope, line)

    def _forward(self, text: str, scope: Scope, line: int) -> None:
        parsed = _parse_expression(text)
        if isinstance(parsed, ast.expr):
            self.type_expression(parsed, scope, line)

    def _subscript(self, node: ast.Subscript, scope: Scope, line: int | None) -> None:
        """`X[...]`: `Literal` arguments and `Annotated` metadata are plain expressions, other elements types."""
        self._plain(node.value, scope, line)
        head = self._head(node.value, scope)
        elements = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        for i, element in enumerate(elements):
            if head == "Literal" or (head == "Annotated" and i > 0):
                self._plain(element, scope, line)
            else:
                self._element(element, scope, line)

    def _element(self, node: ast.expr, scope: Scope, line: int | None) -> None:
        if isinstance(node, ast.List):
            for element in node.elts:
                self._element(element, scope, line)
        else:
            self.type_expression(node, scope, line)

    def comment(self, root: CommentRoot, line: int) -> None:
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


def _comment_lines(roots: list[CommentRoot], text: str) -> Iterator[tuple[CommentRoot, int]]:
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


def check_explicit_any(path: Path, source: str) -> list[tuple[int, str]]:
    """One `compliance.explicit-any` finding, with its line, per reference to `Any` in a file that parses."""
    root, parts, is_package = _location(path.resolve())
    tree, text = _parse_typed(source)
    module = Module(tree, parts, is_package)
    resolver = Resolver(_import_root_finder(root))
    resolver.modules[module.dotted] = module
    reader = _Reader(resolver, module)
    for annotation, scope in module.binder.annotations:
        reader.type_expression(annotation, scope, None)
    for comment, line in _comment_lines(module.binder.comments, text):
        reader.comment(comment, line)
    facts = language("python")
    return [
        (line, message("compliance.explicit-any", path=str(path), line=line, any=facts["any_type"], top=facts["top_type"]))
        for line in reader.lines()
    ]
