"""The portable regex subset (regex-subset.md)."""

from __future__ import annotations

import re
import string

_CLASS_ESCAPES = frozenset("dDwWsS")
_PUNCTUATION = frozenset(string.punctuation)
_BOUNDS_RE = re.compile(r"\{\d+(?:,\d*)?\}")


def _escape_ok(ch: str) -> bool:
    return ch in _CLASS_ESCAPES or ch in _PUNCTUATION


def _class_end(pattern: str, start: int) -> int | None:
    """Index of the `]` closing the class opened at `start`, or None when not portable."""
    i = start + 1
    if pattern.startswith("^", i):
        i += 1
    if pattern.startswith("]", i):
        return None
    while i < len(pattern):
        ch = pattern[i]
        if ch == "]":
            return i
        if ch == "[":
            return None
        if ch == "\\":
            if i + 1 >= len(pattern) or not _escape_ok(pattern[i + 1]):
                return None
            i += 2
            continue
        i += 1
    return None


def _quantifier_end(pattern: str, i: int) -> int | None:
    """Index after the quantifier at `i` (plus an optional lazy `?`), or None when not portable."""
    if pattern[i] == "{":
        m = _BOUNDS_RE.match(pattern, i)
        if m is None:
            return None
        i = m.end()
    else:
        i += 1
    if pattern.startswith("?", i):
        i += 1
    if i < len(pattern) and pattern[i] in "*+?{":
        return None
    return i


def _scan(pattern: str) -> bool:
    i = 0
    quantifiable = False
    while i < len(pattern):
        ch = pattern[i]
        if ch in "*+?{":
            end = _quantifier_end(pattern, i) if quantifiable else None
            if end is None:
                return False
            i, quantifiable = end, False
            continue
        if ch == "\\":
            nxt = pattern[i + 1] if i + 1 < len(pattern) else ""
            if nxt != "b" and not _escape_ok(nxt):
                return False
            i, quantifiable = i + 2, nxt != "b"
        elif ch == "[":
            end = _class_end(pattern, i)
            if end is None:
                return False
            i, quantifiable = end + 1, True
        elif ch == "(":
            if pattern.startswith("(?", i) and not pattern.startswith("(?:", i):
                return False
            i, quantifiable = i + (3 if pattern.startswith("(?:", i) else 1), False
        elif ch in "}]":
            return False
        else:
            i, quantifiable = i + 1, ch not in "^$|"
    return True


def is_portable_regex(pattern: str) -> bool:
    try:
        re.compile(pattern)
    except re.error:
        return False
    return _scan(pattern)
