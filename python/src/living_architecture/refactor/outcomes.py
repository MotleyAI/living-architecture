"""A rename rule's decision on each site it examines: rewrite, blind spot, leftover or unrelated, never none."""

from __future__ import annotations

import ast
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict

from living_architecture.contract import message
from living_architecture.refactor.member_scan import Blindspot, FormCall, receiver_text
from living_architecture.refactor.mentions import Mention, docstrings
from living_architecture.refactor.python_source import SourceFile
from living_architecture.refactor.text_edits import TextEdit


class Finding(BaseModel):
    """A line to print on stderr, at a position of a project file."""

    model_config = ConfigDict(frozen=True)

    path: str
    line: int
    col: int
    text: str


class Outcome(BaseModel):
    """One examined site of file `rel` and what its rule decided: the edits of a rewrite, the line of a blind spot
    or a leftover, nothing for an unrelated site."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["rewrite", "blindspot", "leftover", "unrelated"]
    rel: str
    span: tuple[int, int]
    edits: tuple[TextEdit, ...] = ()
    finding: Finding | None = None


def _leftover(rel: str, source: SourceFile, span: tuple[int, int], where: str, old: str) -> Outcome:
    line = source.line(span[0])
    text = message("refactor.leftover", path=rel, line=line, where=where, old=old)
    return Outcome(kind="leftover", rel=rel, span=span, finding=Finding(path=rel, line=line, col=span[0], text=text))


def string_member_outcome(rel: str, source: SourceFile, call: FormCall, renamed: list[bool], old: str, new: str) -> Outcome:
    """A member form whose lookup lands on declarations (`renamed`: whether each is renamed): rewritten when all
    are, unrelated when none is, else a mixed-target blind spot."""
    span = call.literal
    if not any(renamed):
        return Outcome(kind="unrelated", rel=rel, span=span)
    if all(renamed):
        return Outcome(kind="rewrite", rel=rel, span=span, edits=(TextEdit(path=rel, start=span[0], end=span[1], new_text=new),))
    assert call.obj is not None
    line = call.call.lineno
    text = message("refactor.mixed-target", path=rel, line=line, receiver=receiver_text(source, call.obj), attr=old)
    finding = Finding(path=rel, line=line, col=source.offset(line, call.call.col_offset), text=text)
    return Outcome(kind="blindspot", rel=rel, span=span, finding=finding)


def target_outcome(
    rel: str, source: SourceFile, call: FormCall, *, project_target: bool, renamed: list[bool] | None, member: bool,
    old: str, new: str,
) -> Outcome:
    """A dotted target (`renamed`: whether each segment resolves to a renamed declaration, None when it does not
    resolve): its renamed segments rewritten, else unrelated; unresolved, a blind spot in a member rename's project
    target, else a leftover."""
    span = call.literal
    if renamed is None:
        if not (project_target and member):
            return _leftover(rel, source, span, "patch target", old)
        line = source.line(span[0])
        text = message("refactor.unresolved-target", path=rel, line=line, target=call.text, attr=old)
        return Outcome(kind="blindspot", rel=rel, span=span, finding=Finding(path=rel, line=line, col=span[0], text=text))
    edits: list[TextEdit] = []
    offset = span[0]
    for segment, is_renamed in zip(call.text.split("."), renamed, strict=True):
        if is_renamed:
            edits.append(TextEdit(path=rel, start=offset, end=offset + len(segment), new_text=new))
        offset += len(segment) + 1
    return Outcome(kind="rewrite" if edits else "unrelated", rel=rel, span=span, edits=tuple(edits))


def blindspot_outcome(rel: str, source: SourceFile, spot: Blindspot, old: str) -> Outcome:
    """An untyped receiver of the name: its access, or a string form's literal."""
    col = source.offset(spot.line, spot.col)
    text = message("compliance.attr-blindspot", path=rel, line=spot.line, receiver=spot.receiver, attr=old, type=spot.kind)
    return Outcome(kind="blindspot", rel=rel, span=spot.literal or (col, col), finding=Finding(path=rel, line=spot.line, col=col, text=text))


def mention_outcome(rel: str, mention: Mention, *, rewrite: bool, old: str, new: str) -> Outcome:
    """A `--docs` mention: rewritten, else listed."""
    span = (mention.start, mention.end)
    if rewrite:
        return Outcome(kind="rewrite", rel=rel, span=span, edits=(TextEdit(path=rel, start=span[0], end=span[1], new_text=new),))
    text = message("refactor.leftover", path=rel, line=mention.line, where=mention.where, old=old)
    return Outcome(kind="leftover", rel=rel, span=span, finding=Finding(path=rel, line=mention.line, col=span[0], text=text))


def literal_outcomes(rel: str, source: SourceFile, old: str, handled: Callable[[int, int], bool]) -> list[Outcome]:
    """Each string literal whose whole value is `old` (not a docstring or f-string part) and that no other rule
    `handled`: a leftover."""
    if source.tree is None:
        return []
    skipped = {id(d) for d in docstrings(source.tree)}
    skipped |= {id(v) for n in ast.walk(source.tree) if isinstance(n, ast.JoinedStr) for v in n.values}
    out: list[Outcome] = []
    for node in ast.walk(source.tree):
        if isinstance(node, ast.Constant) and node.value == old and isinstance(node.value, str) and id(node) not in skipped:
            span = source.span(node)
            if not handled(*span):
                out.append(_leftover(rel, source, span, "string", old))
    return sorted(out, key=lambda o: o.span)
