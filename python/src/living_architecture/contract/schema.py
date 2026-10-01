"""Schema validation and default materialization."""

from __future__ import annotations

import copy
from typing import Any

from jsonschema import Draft202012Validator


def validate(schema: dict[str, Any], data: Any) -> list[str]:
    """Sorted `key.path: message` lines, one per violation; empty when valid."""
    errors = []
    for error in Draft202012Validator(schema).iter_errors(data):
        path = ".".join(str(part) for part in error.absolute_path)
        errors.append(f"{path}: {error.message}" if path else error.message)
    return sorted(errors)


def _has_defaults(schema: dict[str, Any]) -> bool:
    return any("default" in sub or _has_defaults(sub) for sub in schema.get("properties", {}).values())


def _fill(schema: dict[str, Any], value: object) -> object:
    if not isinstance(value, dict):
        return value
    out = dict(value)
    for key, sub in schema.get("properties", {}).items():
        if key in out:
            out[key] = _fill(sub, out[key])
        elif "default" in sub:
            out[key] = copy.deepcopy(sub["default"])
        elif _has_defaults(sub):
            out[key] = _fill(sub, {})
    return out


def materialize_defaults(schema: dict[str, Any], data: object) -> Any:
    """`data` (None = missing document) with schema defaults filled in; explicit values are kept."""
    return _fill(schema, {} if data is None else data)
