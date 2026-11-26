"""The 0.4.0 step of `la-arch-migrate`: `conventions.exempt` moves, as text, to a top-level `exempt` key."""

from __future__ import annotations

import re
from typing import Any

from living_architecture.contract import message
from trmv.contract import YAMLError, load_yaml, normalize

_KEY_LINE = re.compile(r"conventions:[ \t]*(?:#.*)?")
_EXEMPT_LINE = re.compile(r"exempt:(?:[ \t]|$)")
_FORMAT_LINE = re.compile(r"format:[ \t]")
_SEQUENCE_ITEM = re.compile(r"-(?:[ \t]|$)")
_MERGE_KEY = re.compile(r"(?:<<|!!merge|!<tag:yaml\.org,2002:merge>)[ \t]*:")
# `&`, `*` or `!` where a node starts: an anchor, an alias or a tag.
_NODE_PROPERTIES = (
    re.compile(r"^[ \t]*[&*!]", re.MULTILINE),
    re.compile(r"[\[{,][ \t]*[&*!]"),
    re.compile(r"(?:^|[ \t])[-?][ \t]+[&*!]", re.MULTILINE),
    re.compile(r":[ \t]+[&*!]"),
)
_LINE_BREAK = re.compile(r"(?<=\n)|(?<=\r)(?!\n)")


class ExemptNotMigratable(Exception):
    """`conventions.exempt` cannot be moved faithfully."""

    def __init__(self) -> None:
        super().__init__(message("arch-migrate.exempt-by-hand"))


def _quoted_step(text: str, i: int, quote: str) -> tuple[str, int, str | None]:
    """The masked piece at `text[i]` inside a `quote` scalar, the characters it spans, and the open quote after it."""
    char = text[i]
    if char == "\\" and quote == '"' and i + 1 < len(text):
        return ("xx" if text[i + 1] not in "\r\n" else "x" + text[i + 1]), 2, quote
    if char == quote == "'" and text[i + 1 : i + 2] == "'":
        return "xx", 2, quote
    return (char if char in "\r\n" else "x"), 1, (None if char == quote else quote)


def _plain_step(text: str, i: int) -> tuple[str, int, str | None]:
    """The masked piece at `text[i]` outside quotes, the characters it spans, and the open quote after it."""
    char = text[i]
    if char in "'\"":
        return "x", 1, char
    if char == "#" and (i == 0 or text[i - 1] in " \t\r\n"):
        end = i
        while end < len(text) and text[end] not in "\r\n":
            end += 1
        return "", end - i, None
    return char, 1, None


def _masked(text: str) -> str:
    """`text` with quoted scalars blanked and comments removed, line breaks kept."""
    out: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(text):
        piece, size, quote = _plain_step(text, i) if quote is None else _quoted_step(text, i, quote)
        out.append(piece)
        i += size
    return "".join(out)


def _lines(text: str) -> list[str]:
    """`text` split after each `\r\n`, `\r` or `\n`, every break kept."""
    return [line for line in _LINE_BREAK.split(text) if line]


def _bare(line: str) -> str:
    return line.rstrip("\r\n")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _blank(line: str) -> bool:
    return not line.strip()


def _comment(line: str) -> bool:
    return line.strip().startswith("#")


def _dedent(line: str, by: int) -> str:
    return line[min(by, _indent(line)) :]


def _entry_span(lines: list[str], key: int) -> tuple[int, int, int]:
    """The conventions body's child indent and the `exempt` entry's line span; ExemptNotMigratable if absent."""
    end = key + 1
    while end < len(lines) and (_blank(lines[end]) or _comment(lines[end]) or _indent(lines[end]) > 0):
        end += 1
    children = [i for i in range(key + 1, end) if not _blank(lines[i]) and not _comment(lines[i])]
    if not children:
        raise ExemptNotMigratable()
    indent = _indent(lines[children[0]])
    if any(_MERGE_KEY.match(_masked(lines[i]).strip()) for i in children if _indent(lines[i]) == indent):
        raise ExemptNotMigratable()
    starts = [i for i in children if _indent(lines[i]) == indent and _EXEMPT_LINE.match(_bare(lines[i])[indent:])]
    if len(starts) != 1:
        raise ExemptNotMigratable()
    start = starts[0]
    inline = lines[start][indent + len("exempt:") :].strip()
    stop = start + 1
    while stop < end:
        line = lines[stop]
        sequence_item = not inline and _indent(line) == indent and _SEQUENCE_ITEM.match(_bare(line)[indent:])
        if not (_blank(line) or _indent(line) > indent or sequence_item):
            break
        stop += 1
    while _blank(lines[stop - 1]):
        stop -= 1
    return indent, start, stop


def _expected(data: dict[Any, Any], current: str) -> dict[Any, Any]:
    conventions = {k: v for k, v in data["conventions"].items() if k != "exempt"}
    expected = {**data, "format": current, "exempt": data["conventions"]["exempt"]}
    if conventions:
        expected["conventions"] = conventions
    else:
        del expected["conventions"]
    return expected


def move_exempt(text: str, current: str) -> str:
    """`text`, stamped at `current`, with `conventions.exempt` moved to directly after the `format` line."""
    try:
        data = load_yaml(text)
    except YAMLError:
        return text
    conventions = data.get("conventions") if isinstance(data, dict) else None
    if not isinstance(conventions, dict) or "exempt" not in conventions:
        return text
    if "exempt" in data:
        raise ExemptNotMigratable()
    lines = _lines(text)
    keys = [i for i, line in enumerate(lines) if line.startswith("conventions:")]
    if len(keys) != 1 or not _KEY_LINE.fullmatch(_bare(lines[keys[0]])):
        raise ExemptNotMigratable()
    key = keys[0]
    indent, start, stop = _entry_span(lines, key)
    entry = lines[start:stop]
    value = re.sub(r"\r\n?", "\n", _masked("".join(entry)[indent + len("exempt") :]))
    if any(pattern.search(value) for pattern in _NODE_PROPERTIES):
        raise ExemptNotMigratable()
    rest = lines[:start] + lines[stop:]
    body = rest[key + 1 :]
    if not any(not _blank(line) and not _comment(line) and _indent(line) > 0 for line in body[: _body_end(body)]):
        del rest[key]
    result = _insert_after_format(rest, [_dedent(line, indent) for line in entry])
    try:
        migrated = load_yaml(result)
    except YAMLError as exc:
        raise ExemptNotMigratable() from exc
    if normalize(migrated) != normalize(_expected(data, current)):
        raise ExemptNotMigratable()
    return result


def _insert_after_format(lines: list[str], entry: list[str]) -> str:
    """`lines` joined with `entry` inserted after the one `format` line, breaks completed in its style."""
    formats = [i for i, line in enumerate(lines) if _FORMAT_LINE.match(line)]
    if len(formats) != 1:
        raise ExemptNotMigratable()
    at = formats[0]
    ending = re.search(r"\r?\n$", lines[at])
    newline = ending.group() if ending else "\n"
    moved = [line if line.endswith(("\n", "\r")) else line + newline for line in entry]
    head = [*lines[:at], lines[at] + ("" if ending else newline)]
    return "".join(head + moved + lines[at + 1 :])


def _body_end(body: list[str]) -> int:
    """The length of the leading run of `body` that still belongs to the `conventions` mapping."""
    end = 0
    while end < len(body) and (_blank(body[end]) or _comment(body[end]) or _indent(body[end]) > 0):
        end += 1
    return end
