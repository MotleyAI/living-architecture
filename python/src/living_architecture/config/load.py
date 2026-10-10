"""Loading `living-architecture.yaml`, with `living-architecture.local.yaml` merged over it, into the typed config."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from living_architecture.contract import (
    YAMLError,
    config_file,
    is_portable_regex,
    load_yaml,
    local_config_file,
    materialize_defaults,
    schema,
    validate,
)

CONFIG_FILENAME = config_file()


class ConfigError(Exception):
    """The config file is unreadable or invalid."""


class RawConfig(BaseModel):
    """The committed data with the local file merged over it, before `resolve`."""

    model_config = ConfigDict(frozen=True)

    data: Any
    overrides: list[str]
    has_committed: bool
    has_local: bool


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SonarConfig(_Strict):
    project_key: str | None


class ReviewersConfig(_Strict):
    codex: bool
    sonar: SonarConfig


class TypecheckConfig(_Strict):
    python: str | None
    typescript: str | None


class CommandsConfig(_Strict):
    test: str | None
    lint: str | None
    typecheck: TypecheckConfig


class ConventionsConfig(_Strict):
    text_ratio_max: float
    exempt: list[str]
    rules: list[str]


class LaConfig(_Strict):
    """The resolved config; built only by `resolve`, so every default comes from the schema."""

    tracker: Literal["linear", "github", "none"]
    openspec: bool
    architecture: bool
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


def _raw(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return load_yaml(path.read_text(encoding="utf-8"))
    except YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc


def _merge(base: Any, over: Any) -> Any:
    if not (isinstance(base, dict) and isinstance(over, dict)):
        return over
    return {**base, **{key: _merge(base.get(key), value) for key, value in over.items()}}


def _leaves(sub: dict[str, Any], data: dict[str, Any], prefix: str = "") -> list[str]:
    """The dotted keys `data` sets, in the schema's property order."""
    out: list[str] = []
    for key, prop in sub["properties"].items():
        if key not in data:
            continue
        if "properties" in prop and isinstance(data[key], dict):
            out += _leaves(prop, data[key], f"{prefix}{key}.")
        else:
            out.append(f"{prefix}{key}")
    return out


def load_raw(root: Path) -> RawConfig:
    """Both files read and the local one checked against its schema; ConfigError naming the faulty file."""
    committed = _raw(root / config_file())
    local_path = root / local_config_file()
    local = _raw(local_path)
    overrides: list[str] = []
    data = committed
    if local is not None:
        if not isinstance(local, dict):
            raise ConfigError(f"{local_path}: top level must be a mapping")
        local_schema = schema("living-architecture.local")
        errors = validate(local_schema, local)
        if errors:
            raise ConfigError(f"{local_path}: {'; '.join(errors)}")
        overrides = _leaves(local_schema, local)
        if committed is None or isinstance(committed, dict):
            data = _merge(committed or {}, local)
    return RawConfig(
        data=data,
        overrides=overrides,
        has_committed=(root / config_file()).is_file(),
        has_local=local_path.is_file(),
    )


def load_config(root: Path) -> LaConfig:
    """Config at `root`; defaults when neither file exists."""
    data = load_raw(root).data
    try:
        return resolve(data)
    except ValueError as exc:
        raise ConfigError(f"{root / config_file()}: {exc}") from exc


def explicit_typecheck(root: Path) -> set[str]:
    """The languages `commands.typecheck` sets explicitly (to a command or null); the config must be valid."""
    data = load_raw(root).data
    commands = data.get("commands") if isinstance(data, dict) else None
    typecheck = commands.get("typecheck") if isinstance(commands, dict) else None
    return set(typecheck) if isinstance(typecheck, dict) else set()
