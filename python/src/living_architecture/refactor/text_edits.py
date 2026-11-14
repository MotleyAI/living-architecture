"""Character-span edits over one snapshot of each file."""

from __future__ import annotations

from itertools import pairwise

from pydantic import BaseModel, ConfigDict


class OverlappingEdits(Exception):
    """Two different edits touch the same characters of `path`."""

    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.path = path


class TextEdit(BaseModel):
    """Replace characters `[start, end)` of `path` with `new_text`."""

    model_config = ConfigDict(frozen=True)

    path: str
    start: int
    end: int
    new_text: str


def merge_edits(edits: list[TextEdit]) -> list[TextEdit]:
    """`edits` deduplicated and sorted by path, then start; overlapping different edits raise `OverlappingEdits`."""
    ordered = sorted(set(edits), key=lambda e: (e.path, e.start, e.end, e.new_text))
    for prev, cur in pairwise(ordered):
        if prev.path == cur.path and cur.start < prev.end:
            raise OverlappingEdits(cur.path)
    return ordered


def apply_edits(text: str, edits: list[TextEdit]) -> str:
    """`text` with `edits` (one file's, merged) applied."""
    out: list[str] = []
    pos = 0
    for edit in edits:
        out += [text[pos : edit.start], edit.new_text]
        pos = edit.end
    return "".join(out) + text[pos:]
