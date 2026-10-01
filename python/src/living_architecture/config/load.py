"""Loading `living-architecture.yaml` at the repo root into the typed config."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from living_architecture.contract import (
    YAMLError,
    is_portable_regex,
    load_yaml,
    materialize_defaults,
    schema,
    validate,
)

CONFIG_FILENAME = "living-architecture.yaml"


class ConfigError(Exception):
    """The config file is unreadable or invalid."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SonarConfig(_Strict):
    enabled: bool
    project_key: str | None


class ReviewersConfig(_Strict):
    coderabbit: bool
    sonar: SonarConfig


class CommandsConfig(_Strict):
    test: str | None
    lint: str | None


class ConventionsConfig(_Strict):
    text_ratio_max: float
    exempt: list[str]


class LaConfig(_Strict):
    """The resolved config; built only by `resolve`, so every default comes from the schema."""

    reviewers: ReviewersConfig
    issue_key_pattern: str
    commands: CommandsConfig
    conventions: ConventionsConfig

    def issue_key_re(self) -> re.Pattern[str]:
        return re.compile(self.issue_key_pattern)


def resolve(data: Any) -> LaConfig:
    """Validate raw config data (None = no file) and fill the schema defaults; ValueError if invalid."""
    config_schema = schema("living-architecture")
    if data is not None and not isinstance(data, dict):
        raise ValueError("top level must be a mapping")
    errors = validate(config_schema, {} if data is None else data)
    if errors:
        raise ValueError("; ".join(errors))
    resolved = materialize_defaults(config_schema, data)
    if not is_portable_regex(resolved["issue_key_pattern"]):
        raise ValueError(
            f"issue_key_pattern {resolved['issue_key_pattern']!r} is not in the portable regex subset"
        )
    return LaConfig.model_validate(resolved)


def find_repo_root(start: Path) -> Path:
    """Nearest ancestor of `start` (inclusive) containing `.git`, else `start`."""
    start = start.resolve()
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


def load_config(root: Path) -> LaConfig:
    """Config at `root`; defaults when the file is absent."""
    path = root / CONFIG_FILENAME
    data = None
    if path.is_file():
        try:
            data = load_yaml(path.read_text(encoding="utf-8"))
        except YAMLError as exc:
            raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    try:
        return resolve(data)
    except ValueError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
