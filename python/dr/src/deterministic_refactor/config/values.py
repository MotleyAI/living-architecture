"""`get` and `show` of a config command: print resolved config values for skills and scripts."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from deterministic_refactor.config.languages import language_fact, repo_languages
from deterministic_refactor.config.load import ConfigError, LanguageSettings, load_with_languages
from deterministic_refactor.contract import message


class ConfigView(BaseModel):
    """A resolved config as a config command prints it: its values, the keys a local file overrides (in
    `local_file`), and what language detection reads."""

    model_config = ConfigDict(frozen=True)

    values: dict[str, Any]
    overrides: list[str] = []
    local_file: str | None = None
    languages: LanguageSettings


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


def _with_view(prog: str, root: Path, load: Callable[[Path], ConfigView], action: Callable[[ConfigView], int]) -> int:
    try:
        view = load(root)
    except ConfigError as exc:
        print(message("config.error", prog=prog, error=str(exc)), file=sys.stderr)
        return 1
    return action(view)


def run_show(prog: str, root: Path, load: Callable[[Path], ConfigView]) -> int:
    """`show`: the resolved config as JSON, then one stderr note per key a local file overrides."""

    def show(view: ConfigView) -> int:
        print(json.dumps(view.values, indent=2))
        for key in view.overrides:
            print(message("config.local-override", prog=prog, key=key, file=view.local_file), file=sys.stderr)
        return 0

    return _with_view(prog, root, load, show)


def _languages(prog: str, root: Path, view: ConfigView) -> int:
    if not (root / ".git").exists():
        print(message("config.not-git", prog=prog), file=sys.stderr)
        return 2
    try:
        languages = repo_languages(root, view.languages)
    except ConfigError as exc:
        print(message("config.error", prog=prog, error=str(exc)), file=sys.stderr)
        return 2
    print(format_value(languages))
    return 0


def _value(view: ConfigView, key: str) -> Any:
    lang_key = key.split(".")
    if lang_key[0] == "lang" and len(lang_key) == 3:
        return language_fact(lang_key[1], lang_key[2])
    if lang_key[0] == "lang":
        raise KeyError(key)
    return _lookup(view.values, key)


def run_get(prog: str, root: Path, key: str, load: Callable[[Path], ConfigView]) -> int:
    """`get KEY`: one value by dotted key; `languages` the repo languages, `lang.<language>.<key>` a language fact."""

    def get(view: ConfigView) -> int:
        if key == "languages":
            return _languages(prog, root, view)
        try:
            print(format_value(_value(view, key)))
        except KeyError:
            print(message("config.unknown-key", prog=prog, key=key), file=sys.stderr)
            return 2
        return 0

    return _with_view(prog, root, load, get)


def dr_view(root: Path) -> ConfigView:
    """dr's config at `root`, as `dr-config` prints it."""
    config, languages = load_with_languages(root)
    return ConfigView(values=config.model_dump(), languages=languages)
