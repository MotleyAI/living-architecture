"""`la-typecheck --realign-from`: basedpyright baseline entries carried to where their errors are now."""

from __future__ import annotations

from typing import Any

from living_architecture.lang.baseline import Key, matches, pairs, text_edits
from living_architecture.lang.language_server import utf16_index, utf16_position
from living_architecture.lang.position_map import Edit, map_range

Entries = list[dict[str, Any]]


def _back(edits: list[Edit], current: str, at_ref: str, key: Key) -> Key | None:
    start, end = map_range(edits, utf16_index(current, key[1], key[2]), utf16_index(current, key[3], key[4]))
    if start == end:
        return None
    (start_line, start_column), (end_line, end_column) = utf16_position(at_ref, start), utf16_position(at_ref, end)
    return key[0], start_line, start_column, end_line, end_column


def back_key(current: str, at_ref: str, key: Key) -> Key | None:
    """`key`, a diagnostic of `current`, at its range in `at_ref`; None when that range is empty."""
    return _back(text_edits(current, at_ref), current, at_ref, key)


def _in_order(index: int, at: tuple[int, int], taken: list[tuple[int, tuple[int, int]]]) -> bool:
    """Entry `index` lies after every taken entry of an earlier position and before every one of a later position."""
    return all(other < index if position < at else other > index for other, position in taken if position != at)


def realigned(entries: Entries, matched: list[Key], unmatched: list[Key], current: str, at_ref: str) -> Entries:
    """A file's entries, each one an unmatched diagnostic takes given that diagnostic's columns and line count. A
    diagnostic takes the first entry no diagnostic has that equals it at its range in `at_ref` and whose place in the
    list agrees with the order of the diagnostics there."""
    edits = text_edits(current, at_ref)
    used: set[int] = set()
    taken: list[tuple[int, tuple[int, int]]] = []
    for index, key in pairs(entries, matched):
        used.add(index)
        back = _back(edits, current, at_ref, key)
        if back is not None:
            taken.append((index, (back[1], back[2])))
    out = list(entries)
    for key in unmatched:
        back = _back(edits, current, at_ref, key)
        if back is None:
            continue
        at = (back[1], back[2])
        index = next((i for i, entry in enumerate(entries)
                      if i not in used and matches(entry, back) and _in_order(i, at, taken)), None)
        if index is None:
            continue
        used.add(index)
        taken.append((index, at))
        rng = dict(entries[index].get("range", {}))
        rng["startColumn"], rng["endColumn"] = key[2], key[4]
        if "lineCount" in rng:
            rng["lineCount"] = key[3] - key[1] + 1
        out[index] = {**entries[index], "range": rng}
    return out


def rekeyed(files: dict[str, Entries], renames: dict[str, str]) -> dict[str, Entries]:
    """The baseline's files with each renamed one (`renames`: new path to old) under its new key, after the entries
    that key already holds."""
    targets = {f"./{old}": f"./{new}" for new, old in renames.items()}
    out = {key: list(entries) for key, entries in files.items() if key not in targets}
    for key, entries in files.items():
        if key in targets:
            out.setdefault(targets[key], []).extend(entries)
    return out
