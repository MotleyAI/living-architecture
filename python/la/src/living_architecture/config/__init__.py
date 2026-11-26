"""la's config: `living-architecture.yaml` with `living-architecture.local.yaml` merged over it, into the typed config."""

from __future__ import annotations

import argparse
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from living_architecture.contract import (
    config_file,
    local_config_file,
    manifest,
    materialize_defaults,
    schema,
    validate,
)
from trmv.config import (
    ConfigError,
    ConfigView,
    LanguageSettings,
    RefactorConfig,
    TypecheckConfig,
    check_string_forms,
    explicit_typecheck,
    read_config,
)
from trmv.config.command import run_command as trmv_run_command
from trmv.contract import is_portable_regex


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


class CommandsConfig(_Strict):
    test: str | None
    lint: str | None
    typecheck: TypecheckConfig


class ConventionsConfig(_Strict):
    text_ratio_max: float
    rules: list[str]


class LaConfig(_Strict):
    """The resolved config; built only by `resolve`, so every default comes from the schemas."""

    format: str | None
    exempt: list[str]
    tracker: Literal["linear", "github", "none"]
    openspec: bool
    architecture: bool
    reviewers: ReviewersConfig
    issue_key_pattern: str
    commands: CommandsConfig
    refactor: RefactorConfig
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
        raise ValueError(f"issue_key_pattern {resolved['issue_key_pattern']!r} is not in the portable regex subset")
    check_string_forms(resolved["refactor"]["string_forms"])
    return LaConfig.model_validate(resolved)


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
    committed = read_config(root, config_file())
    local_path = root / local_config_file()
    local = read_config(root, local_config_file())
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


def resolve_raw(root: Path, raw: RawConfig) -> LaConfig:
    """`raw` resolved; ConfigError naming the committed file."""
    try:
        return resolve(raw.data)
    except ValueError as exc:
        raise ConfigError(f"{root / config_file()}: {exc}") from exc


def load_config(root: Path) -> LaConfig:
    """Config at `root`; defaults when neither file exists."""
    return resolve_raw(root, load_raw(root))


def languages_of(config: LaConfig, raw: RawConfig) -> LanguageSettings:
    """`config` as language detection reads it."""
    return LanguageSettings(
        exempt=config.exempt, typecheck=config.commands.typecheck, explicit=explicit_typecheck(raw.data)
    )


def la_view(root: Path) -> ConfigView:
    """la's config at `root`, as `la-config` prints it, from one read of both files."""
    raw = load_raw(root)
    config = resolve_raw(root, raw)
    return ConfigView(
        values=config.model_dump(), overrides=raw.overrides, local_file=local_config_file(),
        languages=languages_of(config, raw),
    )


def run_command(command: str, argv: list[str], handler: Callable[[argparse.Namespace], int]) -> int:
    """`command` of la's manifest run through trmv's command runner, checking la's config file."""
    return trmv_run_command(command, argv, handler, manifest(), config_file())
