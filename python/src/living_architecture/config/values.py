"""`la-config`: print resolved config values for skills and scripts."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from living_architecture.config.load import ConfigError, load_config
from living_architecture.contract import message


def _lookup(data: Any, dotted: str) -> Any:
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(dotted)
        node = node[part]
    return node


def format_value(value: Any) -> str:
    """Shell-friendly: bools lowercase, None empty, containers as JSON."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)


def _with_config(root: Path, action: Callable[[dict[str, Any]], int]) -> int:
    try:
        data = load_config(root).model_dump()
    except ConfigError as exc:
        print(message("config.error", error=str(exc)), file=sys.stderr)
        return 1
    return action(data)


def run_show(root: Path) -> int:
    def show(data: dict[str, Any]) -> int:
        print(json.dumps(data, indent=2))
        return 0

    return _with_config(root, show)


def run_get(root: Path, key: str) -> int:
    def get(data: dict[str, Any]) -> int:
        try:
            print(format_value(_lookup(data, key)))
        except KeyError:
            print(message("config.unknown-key", key=key), file=sys.stderr)
            return 2
        return 0

    return _with_config(root, get)
