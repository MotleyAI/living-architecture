"""The declaration a Python `move-symbol` moves: one top-level declaration of the source file (an `@overload` group as
one), located by a site on its name, and its region of lines."""

from __future__ import annotations

import ast

from living_architecture.contract import message
from living_architecture.refactor.locators import RefactorError
from living_architecture.refactor.python_source import SourceFile, name_end, split_lines
from living_architecture.refactor.static_resolver import Module, node_key

Declaration = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef | ast.Assign | ast.AnnAssign


class MovedSymbol:
    """The top-level statements declaring `name` that move together, and their region `[start, end)` of the text."""

    def __init__(self, name: str, statements: list[Declaration], region: tuple[int, int], keys: set[str]) -> None:
        self.name = name
        self.statements = statements
        self.region = region
        self.keys = keys


def _not_movable(path: str) -> RefactorError:
    return RefactorError(message("refactor.not-movable", path=path))


def _word(text: str, offset: int) -> tuple[int, int] | None:
    """The identifier at `offset`, or ending just before it."""
    start = offset
    while start > 0 and ("_" + text[start - 1]).isidentifier():
        start -= 1
    end = name_end(text, offset)
    return (start, end) if end > start else None


def _declared(source: SourceFile, stmt: ast.stmt) -> tuple[str, tuple[int, int]] | None:
    """The one name a top-level statement declares and its span: a definition, or an assignment to one name."""
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        found = source.name_span(stmt)
        return (stmt.name, found) if found is not None else None
    targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target] if isinstance(stmt, ast.AnnAssign) else []
    if len(targets) == 1 and isinstance(targets[0], ast.Name):
        return targets[0].id, source.span(targets[0])
    return None


def _shares_line(body: list[ast.stmt], index: int) -> bool:
    stmt = body[index]
    lines = range(stmt.lineno, (stmt.end_lineno or stmt.lineno) + 1)
    return any(other is not stmt and (other.lineno in lines or (other.end_lineno or other.lineno) in lines) for other in body)


def _is_overload(node: ast.AST) -> bool:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
        (isinstance(d, ast.Name) and d.id == "overload") or (isinstance(d, ast.Attribute) and d.attr == "overload")
        for d in node.decorator_list
    )


def _overload_group(body: list[ast.stmt], bound: list[ast.AST]) -> list[Declaration] | None:
    """The `@overload` definitions of `name` directly followed by its one other definition, when they are every top-level
    binding of the name."""
    ids = {id(node) for node in bound}
    for start, stmt in enumerate(body):
        if id(stmt) not in ids:
            continue
        end = start
        while end < len(body) and id(body[end]) in ids and _is_overload(body[end]):
            end += 1
        group = body[start : end + 1]
        if end > start and end < len(body) and id(body[end]) in ids and len(group) == len(ids):
            return [s for s in group if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))]
        return None
    return None


def _region(source: SourceFile, statements: list[Declaration]) -> tuple[int, int]:
    """Lines from the first decorator (else the first line), up over `#` lines in column 0, to the last line, down over
    whitespace-only lines."""
    first = statements[0]
    decorators = getattr(first, "decorator_list", [])
    start = decorators[0].lineno if decorators else first.lineno
    lines = split_lines(source.text)
    while start > 1 and lines[start - 2].startswith("#"):
        start -= 1
    end = statements[-1].end_lineno or statements[-1].lineno
    while end < len(lines) and not lines[end].strip():
        end += 1
    stop = source.line_start(end + 1) if end < len(lines) else len(source.text)
    return source.line_start(start), stop


def locate_moved(source: SourceFile, module: Module, offset: int, shown: str) -> MovedSymbol:
    """The declaration at `offset` of the file `shown`; `refactor.not-movable` for any site but the name of one movable
    top-level declaration."""
    tree = source.tree
    word = _word(source.text, offset)
    if tree is None or word is None:
        raise _not_movable(shown)
    hit = next((i for i, stmt in enumerate(tree.body) if (d := _declared(source, stmt)) is not None and d[1] == word), None)
    if hit is None or (isinstance(tree.body[hit], (ast.Assign, ast.AnnAssign)) and _shares_line(tree.body, hit)):
        raise _not_movable(shown)
    stmt = tree.body[hit]
    declared = _declared(source, stmt)
    assert declared is not None
    name = declared[0]
    bound = [node for scope, bound_name, node in module.binder.bound if bound_name == name and scope.owner(name) is module.scope]
    if len(bound) == 1:
        statements: list[Declaration] = [stmt]  # pyright: ignore[reportAssignmentType]
    else:
        group = _overload_group(tree.body, bound)
        if group is None:
            raise _not_movable(shown)
        statements = list(group)
    keys = {node_key(node) for node in bound}
    return MovedSymbol(name, statements, _region(source, statements), keys)
