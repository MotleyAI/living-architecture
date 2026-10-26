"""The shared YAML profile: YAML 1.1 as PyYAML's safe loader reads it, within a closed tag set (last duplicate key wins)."""

from __future__ import annotations

from typing import Any

import yaml

YAMLError = yaml.YAMLError

# What PyYAML's safe constructors raise, unwrapped, for a scalar they cannot construct (`2024-13-01`, `!!int x`).
_CONSTRUCT_ERRORS = (ValueError, KeyError, IndexError, AttributeError, TypeError, OverflowError)


class _ProfileLoader(yaml.SafeLoader):
    """The safe loader without the tags outside the profile's closed set."""


for _name in ("binary", "set", "omap", "pairs"):
    _ProfileLoader.add_constructor(f"tag:yaml.org,2002:{_name}", _ProfileLoader.construct_undefined)


def load_yaml(text: str) -> Any:
    try:
        return yaml.load(text, Loader=_ProfileLoader)
    except _CONSTRUCT_ERRORS as exc:
        raise YAMLError(f"cannot construct a scalar: {exc}") from exc
