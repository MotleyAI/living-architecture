"""Per-repo config, read from `living-architecture.yaml` at the repo root."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

CONFIG_FILENAME = "living-architecture.yaml"
DEFAULT_ISSUE_KEY_PATTERN = r"[A-Z][A-Z0-9]+-\d+"


class ConfigError(Exception):
    """The config file is unreadable or invalid."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SonarConfig(_Strict):
    enabled: bool = False
    project_key: str | None = None

    @model_validator(mode="after")
    def _key_when_enabled(self) -> SonarConfig:
        if self.enabled and not self.project_key:
            raise ValueError("reviewers.sonar.project_key is required when sonar is enabled")
        return self


class ReviewersConfig(_Strict):
    coderabbit: bool = False
    sonar: SonarConfig = SonarConfig()


class CommandsConfig(_Strict):
    test: str | None = None
    lint: str | None = None


class ConventionsConfig(_Strict):
    text_ratio_max: float = Field(default=0.15, gt=0, le=1)
    exempt: list[str] = []


class LaConfig(_Strict):
    reviewers: ReviewersConfig = ReviewersConfig()
    issue_key_pattern: str = DEFAULT_ISSUE_KEY_PATTERN
    commands: CommandsConfig = CommandsConfig()
    conventions: ConventionsConfig = ConventionsConfig()

    @field_validator("issue_key_pattern")
    @classmethod
    def _compiles(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"issue_key_pattern is not a valid regex: {exc}") from exc
        return value

    def issue_key_re(self) -> re.Pattern[str]:
        return re.compile(self.issue_key_pattern)


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
    if not path.is_file():
        return LaConfig()
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    if raw is None:
        return LaConfig()
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    try:
        return LaConfig.model_validate(raw)
    except ValueError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
