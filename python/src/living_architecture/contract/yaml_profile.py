"""The shared YAML profile: YAML 1.1 as PyYAML's safe loader reads it (last duplicate key wins)."""

from __future__ import annotations

from typing import Any

import yaml

YAMLError = yaml.YAMLError

# What PyYAML's safe constructors raise, unwrapped, for a scalar they cannot construct (`2024-13-01`, `!!int x`).
_CONSTRUCT_ERRORS = (ValueError, KeyError, IndexError, AttributeError, TypeError, OverflowError)


def load_yaml(text: str) -> Any:
    try:
        return yaml.safe_load(text)
    except _CONSTRUCT_ERRORS as exc:
        raise YAMLError(f"cannot construct a scalar: {exc}") from exc
