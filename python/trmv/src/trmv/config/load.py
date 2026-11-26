"""Loading the committed config file trmv reads into trmv's typed config, and the helpers la's config loading shares."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from trmv.contract import (
    DuplicateKeyError,
    YAMLError,
    capturing_groups,
    config_files,
    is_portable_regex,
    is_regular_file,
    load_yaml,
    materialize_defaults,
    message,
    os_error_text,
    schema,
    validate,
)


class ConfigError(Exception):
    """The config file is unreadable or invalid."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class TypecheckConfig(_Strict):
    python: str | None
    typescript: str | None


class TrmvCommandsConfig(_Strict):
    test: str | None
    typecheck: TypecheckConfig


class RefactorPythonConfig(_Strict):
    moved_module_stub: str | None


class RefactorConfig(_Strict):
    python: RefactorPythonConfig
    string_forms: list[str]


class TrmvConfig(_Strict):
    """trmv's resolved config; built only by `resolve`, so every default comes from the schema."""

    format: str | None
    exempt: list[str]
    commands: TrmvCommandsConfig
    refactor: RefactorConfig


class LanguageSettings(BaseModel):
    """What repo-language detection reads from a config: exempt paths, checker commands, the ones set explicitly."""

    model_config = ConfigDict(frozen=True)

    exempt: list[str]
    typecheck: TypecheckConfig
    explicit: frozenset[str]


def find_repo_root(start: Path) -> Path:
    """Nearest ancestor of `start` (inclusive) containing `.git`, else `start`."""
    start = start.resolve()
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


def read_config_text(root: Path, name: str) -> str | None:
    """The text of config file `name`, None when it does not exist; ConfigError when it cannot be read."""
    path = root / name
    try:
        if not is_regular_file(path):
            return None
        data = path.read_bytes()
    except OSError as exc:
        raise ConfigError(os_error_text(exc, root, path)) from exc
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigError(message("yaml.invalid", path=name)) from exc


def parse_config(text: str, name: str) -> Any:
    """`text` of config file `name` in the shared YAML profile; ConfigError when it is not valid YAML."""
    try:
        return load_yaml(text)
    except DuplicateKeyError as exc:
        raise ConfigError(message("yaml.invalid-because", path=name, error=str(exc))) from exc
    except YAMLError as exc:
        raise ConfigError(message("yaml.invalid", path=name)) from exc


def read_config(root: Path, name: str) -> Any:
    """Config file `name` parsed, None when it does not exist; ConfigError when unreadable or not YAML."""
    text = read_config_text(root, name)
    return None if text is None else parse_config(text, name)


def _present(path: Path) -> bool:
    """A regular file, or an entry whose probe fails (reading it reports the OS error)."""
    try:
        return is_regular_file(path)
    except OSError:
        return True


def both_files_problem(root: Path) -> str | None:
    """The refusal when every committed config file is at the repo root, else None."""
    files = config_files()
    if all(_present(root / name) for name in files):
        return message("config.both-files", first=files[0], second=files[1])
    return None


def config_source(root: Path) -> str | None:
    """The committed config file trmv reads: the first of the contract's files at the repo root, else None."""
    return next((name for name in config_files() if _present(root / name)), None)


def own_file() -> str:
    """trmv's own config file; the others carry trmv's keys among their package's."""
    return config_files()[0]


def _own_schema() -> dict[str, Any]:
    """The schema of trmv's own config file, named after it."""
    return schema(Path(own_file()).stem)


def _project(sub: dict[str, Any], data: Any) -> Any:
    """`data` with only the keys `sub` defines, recursively through the objects that list their keys."""
    if not isinstance(data, dict) or "properties" not in sub:
        return data
    return {key: _project(sub["properties"][key], value) for key, value in data.items() if key in sub["properties"]}


def trmv_data(data: Any, name: str) -> Any:
    """The trmv keys of config file `name`'s data: all of trmv's own file, and trmv's share of another package's file."""
    return data if name == own_file() or not isinstance(data, dict) else _project(_own_schema(), data)


def check_string_forms(patterns: list[str]) -> None:
    """ValueError unless every pattern is portable and holds exactly one capturing group."""
    for pattern in patterns:
        if not is_portable_regex(pattern):
            raise ValueError(f"refactor.string_forms pattern {pattern} is not in the portable regex subset")
        if capturing_groups(pattern) != 1:
            raise ValueError(f"refactor.string_forms pattern {pattern} must hold exactly one capturing group")


def resolve(data: Any) -> TrmvConfig:
    """Validate trmv's config data (None = no file) and fill the schema defaults; ValueError if invalid."""
    trmv_schema = _own_schema()
    if data is not None and not isinstance(data, dict):
        raise ValueError("top level must be a mapping")
    errors = validate(trmv_schema, {} if data is None else data)
    if errors:
        raise ValueError("; ".join(errors))
    resolved = materialize_defaults(trmv_schema, data)
    check_string_forms(resolved["refactor"]["string_forms"])
    return TrmvConfig.model_validate(resolved)


def load_dr_data(root: Path) -> tuple[Any, str | None]:
    """trmv's share of the config file it reads, and that file's name; (None, None) without one."""
    name = config_source(root)
    return (None, None) if name is None else (trmv_data(read_config(root, name), name), name)


def _resolved(root: Path, data: Any, name: str | None) -> TrmvConfig:
    try:
        return resolve(data)
    except ValueError as exc:
        raise ConfigError(f"{root / str(name)}: {exc}") from exc


def load_config(root: Path) -> TrmvConfig:
    """trmv's config at `root`; defaults without a config file. ConfigError naming the faulty file."""
    return _resolved(root, *load_dr_data(root))


def explicit_typecheck(data: Any) -> frozenset[str]:
    """The languages config `data` sets `commands.typecheck` for explicitly (to a command or null)."""
    commands = data.get("commands") if isinstance(data, dict) else None
    typecheck = commands.get("typecheck") if isinstance(commands, dict) else None
    return frozenset(typecheck) if isinstance(typecheck, dict) else frozenset()


def load_with_languages(root: Path) -> tuple[TrmvConfig, LanguageSettings]:
    """trmv's config at `root`, and that config as language detection reads it, from one read of the file."""
    data, name = load_dr_data(root)
    config = _resolved(root, data, name)
    return config, LanguageSettings(
        exempt=config.exempt, typecheck=config.commands.typecheck, explicit=explicit_typecheck(data)
    )


def language_settings(root: Path) -> LanguageSettings:
    """trmv's config at `root` as language detection reads it."""
    return load_with_languages(root)[1]
