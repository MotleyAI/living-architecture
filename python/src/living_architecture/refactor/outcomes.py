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
    end: int | None = None

    def covers(self, edit: TextEdit) -> bool:
        """Whether `edit` rewrites part of the finding's site (`col`, else `col:end`)."""
        return covers(self.path, self.col, self.end, edit)


def covers(path: str, col: int, end: int | None, edit: TextEdit) -> bool:
    """Whether `edit` rewrites part of the site `col` (else `col:end`) of `path`."""
    stop = col + 1 if end is None else end
    return edit.path == path and edit.start < stop and col < edit.end


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
    return Outcome(kind="leftover", rel=rel, span=span, finding=Finding(path=rel, line=line, col=span[0], end=span[1], text=text))


def string_member_outcome(rel: str, source: SourceFile, call: FormCall, renamed: list[bool], old: str, new: str) -> Outcome:
    """A member form whose lookup lands on declarations (`renamed`: whether each is renamed): rewritten when all
    are, unrelated when none is, else a mixed-target blind spot."""
    span = call.literal
    if not any(renamed):
        return Outcome(kind="unrelated", rel=rel, span=span)
    if all(renamed):
        return Outcome(kind="rewrite", rel=rel, span=span, edits=(TextEdit(path=rel, start=span[0], end=span[1], new_text=new),))
    return mixed_target_outcome(rel, source, call, old)


def mixed_target_outcome(rel: str, source: SourceFile, call: FormCall, old: str) -> Outcome:
    """A member form whose member lands on renamed and unchanged declarations: a blind spot."""
    assert call.obj is not None
    line = call.call.lineno
    text = message("refactor.mixed-target", path=rel, line=line, receiver=receiver_text(source, call.obj), attr=old)
    finding = Finding(path=rel, line=line, col=source.offset(line, call.call.col_offset), text=text)
    return Outcome(kind="blindspot", rel=rel, span=call.literal, finding=finding)


def name_string_outcome(rel: str, span: tuple[int, int], renamed: list[bool], new: str) -> Outcome:
    """A string naming a member whose lookup lands on declarations (`renamed`: whether each is renamed): rewritten
    when one is, else unrelated."""
    if not any(renamed):
        return Outcome(kind="unrelated", rel=rel, span=span)
    return Outcome(kind="rewrite", rel=rel, span=span, edits=(TextEdit(path=rel, start=span[0], end=span[1], new_text=new),))


def module_member_outcome(rel: str, source: SourceFile, call: FormCall, renamed: bool | None, old: str, new: str) -> Outcome:
    """A member form on a module (`renamed`: whether the module's member is a renamed declaration, None when it does
    not resolve): rewritten, unrelated, or listed as a patch target."""
    if renamed is None:
        return _leftover(rel, source, call.literal, "patch target", old)
    return name_string_outcome(rel, call.literal, [renamed], new)


def unverified_read(rel: str, source: SourceFile, span: tuple[int, int], name: str, old: str, at: tuple[str, int]) -> Finding:
    """A read of a name holding a rewritten source literal (at `at`: its file and line) that proves no member."""
    line = source.line(span[0])
    text = message("refactor.unverified-read", path=rel, line=line, name=name, old=old, source_path=at[0], source_line=at[1])
    return Finding(path=rel, line=line, col=span[0], end=span[1], text=text)


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
    text = blindspot_text(rel, spot, old)
    return Outcome(kind="blindspot", rel=rel, span=spot.literal or (col, col), finding=Finding(path=rel, line=spot.line, col=col, text=text))


def blindspot_text(path: str, spot: Blindspot, attr: str) -> str:
    """The finding of a blind spot, by its kind."""
    if spot.site is None:
        return message("compliance.attr-blindspot", path=path, line=spot.line, receiver=spot.receiver, attr=attr, type=spot.kind)
    template = "compliance.string-blindspot-silent" if spot.silent else "compliance.string-blindspot"
    return message(template, path=path, line=spot.line, site=spot.site, receiver=spot.receiver, attr=attr, type=spot.kind)


def mention_outcome(rel: str, mention: Mention, *, rewrite: bool, old: str, new: str) -> Outcome:
    """A `--docs` mention: rewritten, else listed."""
    span = (mention.start, mention.end)
    if rewrite:
        return Outcome(kind="rewrite", rel=rel, span=span, edits=(TextEdit(path=rel, start=span[0], end=span[1], new_text=new),))
    text = message("refactor.leftover", path=rel, line=mention.line, where=mention.where, old=old)
    return Outcome(kind="leftover", rel=rel, span=span,
                   finding=Finding(path=rel, line=mention.line, col=span[0], end=span[1], text=text))


def literal_spans(source: SourceFile) -> dict[str, list[tuple[int, int]]]:
    """The spans of each string literal of `source` by its value, docstrings and f-string parts aside."""
    found: dict[str, list[tuple[int, int]]] = {}
    if source.tree is None:
        return found
    skipped = {id(d) for d in docstrings(source.tree)}
    skipped |= {id(v) for n in source.nodes if isinstance(n, ast.JoinedStr) for v in n.values}
    for node in source.nodes:
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skipped:
            found.setdefault(node.value, []).append(source.span(node))
    return found


def literal_outcomes(rel: str, source: SourceFile, old: str, handled: Callable[[int, int], bool],
                     spans: list[tuple[int, int]] | None = None) -> list[Outcome]:
    """Each string literal whose whole value is `old` (`spans` when known, docstrings and f-string parts aside)
    that no other rule `handled`: a leftover."""
    found = literal_spans(source).get(old, []) if spans is None else spans
    return sorted((_leftover(rel, source, span, "string", old) for span in found if not handled(*span)),
                  key=lambda o: o.span)


def compound_outcome(rel: str, source: SourceFile, span: tuple[int, int], name: str, old: str) -> Outcome:
    """A declaration whose name holds `old` as a word sequence: listed."""
    line = source.line(span[0])
    text = message("refactor.compound", path=rel, line=line, name=name, old=old)
    return Outcome(kind="leftover", rel=rel, span=span, finding=Finding(path=rel, line=line, col=span[0], end=span[1], text=text))


def file_outcome(outcome: Outcome, *, edits: list[TextEdit], blindspots: list[Finding], leftovers: list[Finding]) -> None:
    """File what a rule decided for one site: its edits, and its finding as a blind spot or a leftover."""
    edits.extend(outcome.edits)
    if outcome.kind == "blindspot":
        assert outcome.finding is not None
        blindspots.append(outcome.finding)
    elif outcome.kind == "leftover":
        assert outcome.finding is not None
        leftovers.append(outcome.finding)
