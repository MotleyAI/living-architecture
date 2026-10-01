"""Python source analysis for the conventions gate and the comment counter; returns data only."""

from __future__ import annotations

import ast
import io
import tokenize
from collections.abc import Iterator

from pydantic import BaseModel

_RAISES_CALLEES = ("raises", "assertRaises", "assertRaisesRegex", "assertRaisesRegexp")
_DOC_OWNERS = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


class Detection(BaseModel):
    """A rule hit: `message_id` names the registry template, rendered with `values`."""

    line: int
    rule: str
    message_id: str
    values: dict[str, str | int] = {}


class SourceAnalysis(BaseModel):
    detections: list[Detection]
    text_lines: int
    total_lines: int


class ParseFailure(Exception):
    def __init__(self, line: int, msg: str) -> None:
        super().__init__(msg)
        self.line = line
        self.msg = msg


def _is_docstring(stmt: ast.stmt) -> bool:
    return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)


def _contains_def(node: ast.stmt) -> bool:
    return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for n in ast.walk(node))


def _imports_in(node: ast.stmt) -> list[ast.stmt]:
    return [n for n in ast.walk(node) if isinstance(n, (ast.Import, ast.ImportFrom))]


def _is_import_wrapper(stmt: ast.stmt) -> bool:
    """A module-level ``if``/``try`` that only wraps imports (TYPE_CHECKING, optional deps)."""
    return isinstance(stmt, (ast.If, ast.Try)) and bool(_imports_in(stmt)) and not _contains_def(stmt)


def _imports_in_function(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    """Imports directly inside ``fn``; nested defs are visited separately by the caller."""
    out: list[ast.stmt] = []
    stack: list[ast.stmt] = list(fn.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            out.append(node)
            continue
        stack.extend(child for child in ast.iter_child_nodes(node) if isinstance(child, ast.stmt))
    return out


def _imports_not_at_top(tree: ast.Module) -> Iterator[Detection]:
    prologue_over = False
    late: list[ast.stmt] = []
    for idx, stmt in enumerate(tree.body):
        if _is_docstring(stmt) and idx == 0:
            continue
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            late += [stmt] if prologue_over else []
            continue
        if _is_import_wrapper(stmt):
            late += _imports_in(stmt) if prologue_over else []
            continue
        prologue_over = True
    for imp in late:
        yield Detection(line=imp.lineno, rule="import-not-top", message_id="conventions.import-after-code")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for imp in _imports_in_function(node):
                yield Detection(
                    line=imp.lineno,
                    rule="import-not-top",
                    message_id="conventions.import-in-function",
                    values={"function": node.name},
                )


def _composite_asserts(tree: ast.Module) -> Iterator[Detection]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.BoolOp) and isinstance(node.test.op, ast.And):
            yield Detection(line=node.lineno, rule="composite-assert", message_id="conventions.composite-assert")


def _is_raises_cm(expr: ast.expr) -> bool:
    if not isinstance(expr, ast.Call):
        return False
    func = expr.func
    if isinstance(func, ast.Attribute):
        return func.attr in _RAISES_CALLEES
    return isinstance(func, ast.Name) and func.id in _RAISES_CALLEES


def _raises_single_throw(tree: ast.Module) -> Iterator[Detection]:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.With, ast.AsyncWith)):
            continue
        if not any(_is_raises_cm(item.context_expr) for item in node.items):
            continue
        calls = sum(isinstance(sub, ast.Call) for stmt in node.body for sub in ast.walk(stmt))
        if calls > 1:
            yield Detection(
                line=node.lineno,
                rule="raises-single-throw",
                message_id="conventions.raises-single-throw",
                values={"calls": calls},
            )


def _text_line_numbers(source: str, tree: ast.Module) -> set[int]:
    """Docstring/standalone-string statement spans plus comment-only lines."""
    text: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt) and _is_docstring(node):
            text.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT and not tok.line[: tok.start[1]].strip():
                text.add(tok.start[0])
    except tokenize.TokenError:
        pass
    return text


def analyze(source: str) -> SourceAnalysis:
    """Every rule's detections (in rule order) plus text-only and total line counts."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ParseFailure(exc.lineno or 1, exc.msg or "syntax error") from exc
    detections = [*_imports_not_at_top(tree), *_composite_asserts(tree), *_raises_single_throw(tree)]
    return SourceAnalysis(
        detections=detections,
        text_lines=len(_text_line_numbers(source, tree)),
        total_lines=len(source.splitlines()),
    )


def comment_doc_counts(src: str | None) -> tuple[int, int]:
    """(comment lines, docstring lines); zeros for a missing file."""
    if src is None:
        return 0, 0
    try:
        comment = sum(1 for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type == tokenize.COMMENT)
    except (tokenize.TokenError, SyntaxError):
        comment = 0
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return comment, 0
    doc = 0
    for node in ast.walk(tree):
        if isinstance(node, _DOC_OWNERS) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                doc += (first.end_lineno or first.lineno) - first.lineno + 1
    return comment, doc
