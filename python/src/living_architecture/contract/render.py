"""Template rendering with the canonical repr."""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Mapping

from living_architecture.contract.snapshot import findings

_PLACEHOLDER_RE = re.compile(r"\{\{|\}\}|\{([a-z_]+)(!r)?\}")


def normalize(value: object) -> object:
    """Map a raw YAML value onto the normalized types (str, int, float, bool, None, list, mapping)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [normalize(v) for v in value]
    if isinstance(value, Mapping):
        return {normalize(k): normalize(v) for k, v in value.items()}
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return str(value)


def canonical_repr(value: object) -> str:
    """Python's repr, restricted to normalized values."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(canonical_repr(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{canonical_repr(k)}: {canonical_repr(v)}" for k, v in value.items()) + "}"
    raise TypeError(f"not a normalized value: {type(value).__name__}")


def render_template(template: str, values: Mapping[str, object]) -> str:
    def substitute(m: re.Match[str]) -> str:
        if m.group(1) is None:
            return m.group(0)[0]
        value = normalize(values[m.group(1)])
        return value if isinstance(value, str) and not m.group(2) else canonical_repr(value)

    return _PLACEHOLDER_RE.sub(substitute, template)


def message(template_id: str, **values: object) -> str:
    """The registry template `template_id` rendered with `values`."""
    return render_template(findings()[template_id], values)
