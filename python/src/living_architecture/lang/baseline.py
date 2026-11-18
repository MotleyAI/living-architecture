"""basedpyright's baseline: its entries matched against diagnostics, and the text edits a range maps through."""

from __future__ import annotations

import difflib
from collections import Counter
from pathlib import Path
from typing import Any

from living_architecture.lang.position_map import Edit

Key = tuple[str, int, int, int, int]
"""A diagnostic: its rule and its 0-based start and end line and column."""


def line_starts(lines: list[str]) -> list[int]:
    out = [0]
    for line in lines:
        out.append(out[-1] + len(line))
    return out


def text_edits(old: str, new: str) -> list[Edit]:
    """Edits turning `old` into `new`: the changed lines, then the characters within them."""
    old_lines, new_lines = old.splitlines(True), new.splitlines(True)
    old_at, new_at = line_starts(old_lines), line_starts(new_lines)
    out: list[Edit] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        a, b = old[old_at[i1] : old_at[i2]], new[new_at[j1] : new_at[j2]]
        for inner, a1, a2, b1, b2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if inner != "equal":
                out.append((old_at[i1] + a1, old_at[i1] + a2, b2 - b1))
    return out


def diagnostics(report: dict[str, Any], repo: Path) -> list[tuple[str, Key]]:
    """The report's diagnostics in its order (each file's sorted by start, ties as the checker emits them)."""
    out: list[tuple[str, Key]] = []
    for d in report.get("generalDiagnostics", []):
        path = Path(d["file"]).resolve()
        if not path.is_relative_to(repo):
            continue
        r = d["range"]
        key = (str(d.get("rule", "")), r["start"]["line"], r["start"]["character"], r["end"]["line"], r["end"]["character"])
        out.append((path.relative_to(repo).as_posix(), key))
    return out


def matches(entry: dict[str, Any], key: Key) -> bool:
    r = entry.get("range", {})
    count = r.get("lineCount")
    return (entry.get("code") == key[0] and r.get("startColumn") == key[2] and r.get("endColumn") == key[4]
            and (count is None or count == key[3] - key[1] + 1))


def pairs(entries: list[dict[str, Any]], hidden: list[Key]) -> list[tuple[int, Key]]:
    """Each baselined diagnostic, in position order, with the first unpaired entry after the last one paired whose
    code, columns and line count equal it."""
    out: list[tuple[int, Key]] = []
    last = -1
    for key in hidden:
        k = next((i for i in range(last + 1, len(entries)) if matches(entries[i], key)), None)
        if k is not None:
            out.append((k, key))
            last = k
    return out


def baselined(everything: list[tuple[str, Key]], unbaselined: list[tuple[str, Key]]) -> list[tuple[str, Key]]:
    """The diagnostics the baseline hides: those shown without it, less as many of each as it lets through."""
    shown_alone = Counter(unbaselined)
    out: list[tuple[str, Key]] = []
    for item in everything:
        if shown_alone[item]:
            shown_alone[item] -= 1
        else:
            out.append(item)
    return out
