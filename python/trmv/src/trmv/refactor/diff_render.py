"""A refactor's changes rendered as rope 1.15's change descriptions rendered them, so the printed diff stays the same."""

from __future__ import annotations

import difflib

from deterministic_refactor.contract import message


def _shown(text: str) -> str:
    """`text` with every line ending as `\\n`, as rope reads a file."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def edit_description(rel: str, old: str, new: str) -> str:
    """The unified diff of file `rel` from `old` to `new` (texts as read and as written)."""
    lines = difflib.unified_diff(_shown(old).splitlines(True), _shown(new).splitlines(True), "a/" + rel, "b/" + rel)
    return "".join(lines)


def move_description(rel: str, dest: str) -> str:
    return message("refactor.moved", old=rel, new=dest)
