"""The contract glob dialect: segment-wise, `*` within a segment, `**` for zero or more segments."""

from __future__ import annotations

import re
from functools import cache


@cache
def _segment_re(segment: str) -> re.Pattern[str]:
    return re.compile("".join(".*" if ch == "*" else re.escape(ch) for ch in segment), re.DOTALL)


def _match(pattern: tuple[str, ...], path: tuple[str, ...]) -> bool:
    if not pattern:
        return not path
    head, rest = pattern[0], pattern[1:]
    if head == "**":
        return any(_match(rest, path[i:]) for i in range(len(path) + 1))
    return bool(path) and _segment_re(head).fullmatch(path[0]) is not None and _match(rest, path[1:])


def glob_match(pattern: str, path: str) -> bool:
    return _match(tuple(pattern.split("/")), tuple(path.split("/")) if path else ())
