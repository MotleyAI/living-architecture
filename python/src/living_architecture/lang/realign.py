"""`la-typecheck --realign-from`: basedpyright baseline entries carried to where their errors are now."""

from __future__ import annotations

from array import array
from typing import Any

from living_architecture.lang.baseline import Key, matches, text_edits
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


Wanted = list[tuple[Key, bool]]
"""The shape an entry must have for each diagnostic, with whether that diagnostic is baselined."""


def _paired(entries: Entries, wanted: Wanted) -> list[tuple[int, int]]:
    """(entry, wanted) index pairs in list order that keep the most baselined diagnostics, then take the most
    entries, earliest first."""
    n, m = len(entries), len(wanted)
    gain = [m + 1 if hidden else 1 for _, hidden in wanted]
    width = m + 1
    best = array("q", bytes(8 * (n + 1) * width))
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            at = i * width + j
            take = best[at + width + 1] + gain[j] if matches(entries[i], wanted[j][0]) else 0
            best[at] = max(take, best[at + width], best[at + 1])
    out: list[tuple[int, int]] = []
    i = j = 0
    while i < n and j < m:
        at = i * width + j
        if matches(entries[i], wanted[j][0]) and best[at] == best[at + width + 1] + gain[j]:
            out.append((i, j))
            i, j = i + 1, j + 1
        elif best[at] == best[at + width]:
            i += 1
        else:
            j += 1
    return out


def _taken(entries: Entries, wanted: Wanted) -> list[tuple[int, int]]:
    """`_paired` over the entries and diagnostics between the baselined ones that pair off at both ends: a baselined
    diagnostic at an end pairs with a fitting entry at that end in some best pairing."""
    n, m = len(entries), len(wanted)
    head = 0
    while head < min(n, m) and wanted[head][1] and matches(entries[head], wanted[head][0]):
        head += 1
    tail = 0
    while tail < min(n, m) - head and wanted[m - 1 - tail][1] and matches(entries[n - 1 - tail], wanted[m - 1 - tail][0]):
        tail += 1
    middle = _paired(entries[head : n - tail], wanted[head : m - tail])
    return ([(k, k) for k in range(head)] + [(i + head, j + head) for i, j in middle]
            + [(n - k, m - k) for k in range(tail, 0, -1)])


Diagnostics = list[tuple[Key, bool]]
"""A file's diagnostics in report order, each with whether the baseline hides it."""


def _found(diagnostics: Diagnostics, current: str, at_ref: str) -> list[tuple[Key, Key, bool]]:
    """Each diagnostic an entry can pair with, in report order: itself, the shape its entry has (its own when
    baselined, else its range in `at_ref`), and whether it is baselined. The mapping keeps order, so this is their
    order at `at_ref` too."""
    edits = text_edits(current, at_ref)
    found: list[tuple[Key, Key, bool]] = []
    for key, hidden in diagnostics:
        shape = key if hidden else _back(edits, current, at_ref, key)
        if shape is not None:
            found.append((key, shape, hidden))
    return found


def realigned(entries: Entries, diagnostics: Diagnostics, current: str, at_ref: str) -> Entries:
    """A file's entries, each one an unmatched diagnostic takes given that diagnostic's columns and line count. A
    diagnostic takes an entry that equals it at its range in `at_ref`; the entries taken and the entries of the
    baselined diagnostics lie in the order of their diagnostics."""
    found = _found(diagnostics, current, at_ref)
    out = list(entries)
    for index, at in _taken(entries, [(shape, hidden) for _, shape, hidden in found]):
        key, _, hidden = found[at]
        if hidden:
            continue
        rng = dict(entries[index].get("range", {}))
        rng["startColumn"], rng["endColumn"] = key[2], key[4]
        if "lineCount" in rng:
            rng["lineCount"] = key[3] - key[1] + 1
        out[index] = {**entries[index], "range": rng}
    return out


def merged(held: Entries, moved: Entries, diagnostics: Diagnostics, current: str, at_ref: str) -> Entries:
    """The entries a renamed file's new key held and the ones moved onto it, in the order of the diagnostics they
    pair with (the moved ones pair first); an entry that pairs with none follows its predecessor of its own set."""
    wanted: Wanted = [(shape, hidden) for _, shape, hidden in _found(diagnostics, current, at_ref)]
    of_moved = dict(_taken(moved, wanted))
    left = [j for j in range(len(wanted)) if j not in set(of_moved.values())]
    of_held = {i: left[j] for i, j in _taken(held, [wanted[j] for j in left])}
    placed: list[tuple[tuple[int, int, int], dict[str, Any]]] = []
    for which, (entries, paired) in enumerate(((held, of_held), (moved, of_moved))):
        anchor = -1
        for i, entry in enumerate(entries):
            anchor = paired.get(i, anchor)
            placed.append(((anchor, which, i), entry))
    return [entry for _, entry in sorted(placed, key=lambda item: item[0])]


def rekeyed(files: dict[str, Entries], renames: dict[str, str]) -> dict[str, Entries]:
    """The baseline's files with each renamed one (`renames`: new path to old) under its new key, after the entries
    that key already holds."""
    targets = {f"./{old}": f"./{new}" for new, old in renames.items()}
    out = {key: list(entries) for key, entries in files.items() if key not in targets}
    for key, entries in files.items():
        if key in targets:
            out.setdefault(targets[key], []).extend(entries)
    return out
