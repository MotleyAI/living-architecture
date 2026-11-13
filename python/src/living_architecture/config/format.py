"""The repo format: `format` in the committed `living-architecture.yaml`, the check every gated command runs, the stamp."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from living_architecture.config.load import ConfigError
from living_architecture.contract import (
    YAMLError,
    canonical_repr,
    config_file,
    config_formats,
    load_yaml,
    message,
    normalize,
)

FORMAT_KEY = "format"
_VERSION_RE = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", re.ASCII)
_BLANK = " \t\r"
# A top-level `format` line with one single-line scalar value: its value, then its trailing whitespace and comment.
_FORMAT_LINE = re.compile(
    rf"{FORMAT_KEY}:[ \t]+"
    r"(?P<value>'(?:[^']|'')*'|\"(?:[^\"\\]|\\.)*\"|[^\s#'\"|>{}\[\],&*!%@`](?:[^#]|(?<![ \t])#)*?)"
    r"(?P<rest>[ \t]*(?:#.*)?)"
)


class Committed(BaseModel):
    """The committed config file: its exact text and its top-level mapping, None for an empty document."""

    model_config = ConfigDict(frozen=True)

    text: str
    data: dict[Any, Any] | None


def released_formats() -> list[str]:
    """Every released repo format, oldest first."""
    return config_formats()


def current_format() -> str:
    """The repo format this la reads and writes: the last released one."""
    return config_formats()[-1]


def is_version(value: object) -> bool:
    """Three dot-separated decimal integers without leading zeros."""
    return isinstance(value, str) and _VERSION_RE.fullmatch(value) is not None


def compare_versions(a: str, b: str) -> int:
    """The sign of `a - b`, component by component as integers of any size."""
    for x, y in zip(a.split("."), b.split("."), strict=True):
        if (len(x), x) != (len(y), y):
            return 1 if (len(x), x) > (len(y), y) else -1
    return 0


def read_committed(root: Path) -> Committed | None:
    """The committed file, None without one; ConfigError when it is unreadable, not YAML or not a mapping."""
    path = root / config_file()
    if not path.is_file():
        return None
    try:
        text = path.read_bytes().decode("utf-8")
        data = load_yaml(text)
    except (OSError, UnicodeDecodeError, YAMLError) as exc:
        raise ConfigError(f"{config_file()}: {exc}") from exc
    if data is not None and not isinstance(data, dict):
        raise ConfigError(f"{config_file()}: top level must be a mapping")
    return Committed(text=text, data=data)


def format_problem(data: dict[Any, Any], current: str | None = None) -> str | None:
    """The refusal of a committed mapping's `format`, or None when it declares `current` (default: the current format)."""
    current = current or current_format()
    if FORMAT_KEY not in data:
        return message("format.missing", current=current)
    declared = data[FORMAT_KEY]
    if not is_version(declared):
        return message("format.invalid", value=declared, current=current)
    sign = compare_versions(declared, current)
    if sign == 0:
        return None
    return message("format.newer" if sign > 0 else "format.older", declared=declared, current=current)


def check_format(root: Path) -> str | None:
    """The format check's refusal, or None to go on (also for a committed file it cannot judge)."""
    try:
        committed = read_committed(root)
    except ConfigError:
        return None
    return None if committed is None or committed.data is None else format_problem(committed.data)


def _unordered_repr(value: object) -> str:
    """The canonical repr of a normalized value, with every mapping's entries sorted."""
    if isinstance(value, dict):
        return "{" + ", ".join(sorted(f"{_unordered_repr(k)}: {_unordered_repr(v)}" for k, v in value.items())) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(_unordered_repr(item) for item in value) + "]"
    return canonical_repr(value)


def _insert_at(lines: list[str]) -> int:
    """The index of the first line after the leading comments, blank lines, directives and a `---` marker."""
    for index, line in enumerate(lines):
        content = line.rstrip("\r\n")
        if content.rstrip(_BLANK) == "---":
            return index + 1
        stripped = content.lstrip(_BLANK)
        if stripped and not stripped.startswith("#") and not content.startswith("%"):
            return index
    return len(lines)


def _lines(text: str) -> list[str]:
    """`text` split after each line break; no empty last line."""
    lines = [line + "\n" for line in text.split("\n")]
    lines[-1] = lines[-1][:-1]
    if not lines[-1]:
        lines.pop()
    return lines


def _inserted(text: str, current: str) -> str:
    """`text` with a `format: <current>` line after its leading comments, directives and document marker."""
    first_break = text.find("\n")
    newline = "\r\n" if first_break > 0 and text[first_break - 1] == "\r" else "\n"
    lines = _lines(text)
    index = _insert_at(lines)
    if index == len(lines) and lines and not lines[-1].endswith("\n"):
        lines[-1] += newline
    lines.insert(index, f"{FORMAT_KEY}: {current}{newline}")
    return "".join(lines)


def _replaced(text: str, current: str) -> str | None:
    """`text` with the value on its one top-level `format` line replaced by `current`; None without exactly one."""
    lines = _lines(text)
    found = [i for i, line in enumerate(lines) if line.startswith(f"{FORMAT_KEY}:")]
    if len(found) != 1:
        return None
    line = lines[found[0]]
    content = line.rstrip("\r\n")
    match = _FORMAT_LINE.fullmatch(content)
    if match is None:
        return None
    lines[found[0]] = content[: match.start("value")] + current + match["rest"] + line[len(content) :]
    return "".join(lines)


def stamp_format(text: str, current: str | None = None) -> str | None:
    """`text` declaring `current` (default: the current format): a `format` line inserted or its value replaced,
    verified to change only that key; None when it cannot be."""
    current = current or current_format()
    try:
        before = load_yaml(text)
    except YAMLError:
        return None
    if before is not None and not isinstance(before, dict):
        return None
    stamped = _replaced(text, current) if FORMAT_KEY in (before or {}) else _inserted(text, current)
    if stamped is None:
        return None
    try:
        after = load_yaml(stamped)
    except YAMLError:
        return None
    expected = {**(before or {}), FORMAT_KEY: current}
    return stamped if _unordered_repr(normalize(after)) == _unordered_repr(normalize(expected)) else None
