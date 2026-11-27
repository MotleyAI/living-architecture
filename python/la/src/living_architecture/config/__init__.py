"""la's config: `living-architecture.yaml` with `living-architecture.local.yaml` merged over it, or la's stealth config,
into the typed config."""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from living_architecture.contract import (
    config_file,
    leak_token_groups,
    local_config_file,
    manifest,
    materialize_defaults,
    message,
    schema,
    stealth_path,
    validate,
)
from trmv.config import (
    ConfigError,
    ConfigFile,
    ConfigView,
    LanguageSettings,
    RefactorConfig,
    TypecheckConfig,
    check_string_forms,
    explicit_typecheck,
    find_config,
    read_config,
    stealth_dir,
    stealth_refusal,
    stealth_view,
)
from trmv.config.command import run_command as trmv_run_command
from trmv.contract import is_portable_regex


class RawConfig(BaseModel):
    """The config file's data with the local file merged over it, before `resolve`; `source` is the config file."""

    model_config = ConfigDict(frozen=True)

    data: Any
    overrides: list[str]
    has_committed: bool
    has_local: bool
    source: ConfigFile | None = None


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


class LeaksConfig(_Strict):
    allow: list[str]


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
    leaks: LeaksConfig = LeaksConfig(allow=[])

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


def _leaks(data: Any, source: ConfigFile) -> Any:
    """The config file's data with the stealth config's `leaks.allow` checked and defaulted; ConfigError for `leaks`
    in a root file."""
    name = source.display()
    if not source.stealth:
        if isinstance(data, dict) and "leaks" in data:
            raise ConfigError(message("config.leaks-not-stealth", path=name))
        return data
    data = {} if data is None else data
    leaks = data.get("leaks", {}) if isinstance(data, dict) else None
    if not isinstance(leaks, dict):
        return data
    allow = leaks.get("allow", [])
    waivable = leak_token_groups()[1]
    for token in allow if isinstance(allow, list) else []:
        if token not in waivable:
            raise ConfigError(message("config.leak-not-waivable", path=name, token=token))
    return {**data, "leaks": {**leaks, "allow": allow}}


def load_raw(root: Path) -> RawConfig:
    """The config file and the local one read, the local one checked against its schema; ConfigError naming the
    faulty file. In stealth mode a local file is refused."""
    source = find_config(root, "la")
    name = config_file() if source is None else source.display()
    committed = read_config(root, name)
    if source is not None and source.stealth:
        stealth_refusal(committed, name)
    if source is not None:
        committed = _leaks(committed, source)
    local_path = root / local_config_file()
    if source is not None and source.stealth and local_path.is_file():
        raise ConfigError(message("config.local-in-stealth", file=local_config_file()))
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
        has_committed=source is not None,
        has_local=local_path.is_file(),
        source=source,
    )


def resolve_raw(root: Path, raw: RawConfig) -> LaConfig:
    """`raw` resolved; ConfigError naming the config file."""
    try:
        return resolve(raw.data)
    except ValueError as exc:
        name = config_file() if raw.source is None else raw.source.display()
        raise ConfigError(f"{root / name}: {exc}") from exc


def load_config(root: Path) -> LaConfig:
    """Config at `root`; defaults when neither file exists."""
    return resolve_raw(root, load_raw(root))


def openspec_store_id(directory: Path) -> str:
    """The private OpenSpec store's id: `la-` and the first 12 hex digits of the SHA-256 of la's stealth directory."""
    return "la-" + hashlib.sha256(str(directory).encode("utf-8")).hexdigest()[:12]


def tracks_openspec(root: Path) -> bool:
    """Whether HEAD tracks a path under `openspec/`."""
    try:
        proc = subprocess.run(["git", "ls-tree", "-r", "-z", "--name-only", "HEAD", "--", "openspec/"], cwd=root,
                              capture_output=True, check=False)
    except OSError:
        return False
    return proc.returncode == 0 and bool(proc.stdout)


def private_store(root: Path, cfg: LaConfig, raw: RawConfig) -> Path | None:
    """la's stealth directory when the private OpenSpec store applies, else None."""
    if raw.source is None or not raw.source.stealth or not cfg.openspec or tracks_openspec(root):
        return None
    return stealth_dir(root, "la")


def plans_dir(directory: Path) -> Path:
    """Where the /la:pr flow keeps its plans in stealth mode with openspec false."""
    return directory / stealth_path("plans_dir")


def languages_of(config: LaConfig, raw: RawConfig) -> LanguageSettings:
    """`config` as language detection reads it."""
    return LanguageSettings(
        exempt=config.exempt, typecheck=config.commands.typecheck, explicit=explicit_typecheck(raw.data)
    )


def la_view(root: Path) -> ConfigView:
    """la's config at `root`, as `la-config` prints it, from one read of both files."""
    raw = load_raw(root)
    config = resolve_raw(root, raw)
    values = config.model_dump()
    if raw.source is None or not raw.source.stealth:
        del values["leaks"]
    stealth_file, derived = stealth_view(root, "la")
    store = private_store(root, config, raw)
    derived = {**derived, "openspec_store": "" if store is None else openspec_store_id(store)}
    return ConfigView(
        values=values, overrides=raw.overrides, local_file=local_config_file(),
        languages=languages_of(config, raw), stealth_file=stealth_file, derived=derived,
    )


def run_command(command: str, argv: list[str], handler: Callable[[argparse.Namespace], int]) -> int:
    """`command` of la's manifest run through trmv's command runner, checking la's config file."""
    return trmv_run_command(command, argv, handler, manifest(), "la")
