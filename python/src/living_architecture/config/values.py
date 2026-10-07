"""`la-config`: print resolved config values for skills and scripts."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from living_architecture.config.languages import language_fact, repo_languages
from living_architecture.config.load import ConfigError, LaConfig, load_config
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


def _with_config(root: Path, action: Callable[[LaConfig], int]) -> int:
    try:
        config = load_config(root)
    except ConfigError as exc:
        print(message("config.error", error=str(exc)), file=sys.stderr)
        return 1
    return action(config)


def run_show(root: Path) -> int:
    def show(config: LaConfig) -> int:
        print(json.dumps(config.model_dump(), indent=2))
        return 0

    return _with_config(root, show)


def _languages(root: Path, config: LaConfig) -> int:
    if not (root / ".git").exists():
        print(message("config.not-git"), file=sys.stderr)
        return 2
    try:
        languages = repo_languages(root, config)
    except ConfigError as exc:
        print(message("config.error", error=str(exc)), file=sys.stderr)
        return 2
    print(format_value(languages))
    return 0


def _value(config: LaConfig, key: str) -> Any:
    lang_key = key.split(".")
    if lang_key[0] == "lang" and len(lang_key) == 3:
        return language_fact(lang_key[1], lang_key[2])
    if lang_key[0] == "lang":
        raise KeyError(key)
    return _lookup(config.model_dump(), key)


def run_get(root: Path, key: str) -> int:
    def get(config: LaConfig) -> int:
        if key == "languages":
            return _languages(root, config)
        try:
            print(format_value(_value(config, key)))
        except KeyError:
            print(message("config.unknown-key", key=key), file=sys.stderr)
            return 2
        return 0

    return _with_config(root, get)
