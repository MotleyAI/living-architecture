"""Compound names: a declaration whose name contains the renamed name as a word sequence."""

from __future__ import annotations

import unicodedata


def _upper(char: str) -> bool:
    return unicodedata.category(char) == "Lu"


def word_spans(name: str) -> list[tuple[int, int]]:
    """The spans of `name`'s words: split at `_`, before a capital after a non-capital, and before the last capital of
    a run that a letter other than a capital follows."""
    out: list[tuple[int, int]] = []
    base = 0
    for chunk in name.split("_"):
        start = 0
        for i in range(1, len(chunk)):
            if not _upper(chunk[i]):
                continue
            follows = i + 1 < len(chunk) and not _upper(chunk[i + 1]) and not chunk[i + 1].isdecimal()
            if not _upper(chunk[i - 1]) or follows:
                out.append((base + start, base + i))
                start = i
        if chunk:
            out.append((base + start, base + len(chunk)))
        base += len(chunk) + 1
    return out


def words(name: str) -> list[str]:
    """`name`'s words, as `word_spans` splits it."""
    return [name[start:end] for start, end in word_spans(name)]


def is_compound(name: str, old: str) -> bool:
    """`name` holds `old`'s words in sequence, without case, the last also with an `s` or `es` suffix."""
    wanted = [w.lower() for w in words(old)]
    found = [w.lower() for w in words(name)]
    if not wanted or name == old:
        return False
    last = {wanted[-1], f"{wanted[-1]}s", f"{wanted[-1]}es"}
    for i in range(len(found) - len(wanted) + 1):
        if found[i : i + len(wanted) - 1] == wanted[:-1] and found[i + len(wanted) - 1] in last:
            return True
    return False
