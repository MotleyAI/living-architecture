"""Loading the committed config file trmv reads into trmv's typed config, and the helpers la's config loading shares."""

from __future__ import annotations

import subprocess
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
    stealth_files,
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


class ConfigFile(BaseModel):
    """A config file a command reads, and whether it is a stealth one (in the git common directory)."""

    model_config = ConfigDict(frozen=True)

    path: Path
    stealth: bool

    def display(self) -> str:
        """How messages name it: a root file by its name, a stealth file by its absolute path."""
        return str(self.path) if self.stealth else self.path.name


def common_dir(start: Path) -> Path | None:
    """The absolute git common directory of the working tree holding `start`; None outside git."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=start, capture_output=True, check=False
        )
    except OSError:
        return None
    out = proc.stdout.decode("utf-8", "surrogateescape").rstrip("\n")
    return Path(out) if proc.returncode == 0 and out else None


def stealth_dir(start: Path, package: str) -> Path | None:
    """`package`'s stealth directory under the git common directory of `start`; None outside git."""
    common = common_dir(start)
    if common is None:
        return None
    return next(common / rel for owner, rel in stealth_files() if owner == package).parent


def present_files(root: Path) -> list[ConfigFile]:
    """Every config file present for `root`, in lookup order: the root files, then the stealth files."""
    found = [ConfigFile(path=root / name, stealth=False) for name in config_files() if _present(root / name)]
    common = common_dir(root)
    if common is not None:
        found += [ConfigFile(path=common / rel, stealth=True) for _, rel in stealth_files() if _present(common / rel)]
    return found


def files_problem(root: Path) -> str | None:
    """The refusal when more than one config file is present for `root`, else None."""
    found = present_files(root)
    if len(found) < 2:
        return None
    if not any(f.stealth for f in found):
        files = config_files()
        return message("config.both-files", first=files[0], second=files[1])
    return message("config.multiple-files", files=", ".join(f.display() for f in found))


def _package_file(package: str) -> str:
    return next(Path(rel).name for owner, rel in stealth_files() if owner == package)


def find_config(start: Path, package: str) -> ConfigFile | None:
    """The config file `package`'s commands read at `start`: trmv reads the first present, la only its own file;
    ConfigError when more than one is present."""
    problem = files_problem(start)
    if problem is not None:
        raise ConfigError(problem)
    found = present_files(start)
    if package != "trmv":
        found = [f for f in found if f.path.name == _package_file(package)]
    return found[0] if found else None


def is_stealth(root: Path, package: str = "trmv") -> bool:
    """Whether `package`'s commands at `root` read a stealth config file; ConfigError when several are present."""
    found = find_config(root, package)
    return found is not None and found.stealth


def config_source(root: Path, package: str = "trmv") -> str | None:
    """How messages name the config file `package` reads at `root`, None without one; ConfigError when several."""
    found = find_config(root, package)
    return None if found is None else found.display()


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
    return data if Path(name).name == own_file() or not isinstance(data, dict) else _project(_own_schema(), data)


def stealth_refusal(data: Any, name: str) -> None:
    """ConfigError when stealth config file `name` sets what cannot stay private."""
    if isinstance(data, dict) and data.get("architecture") is True:
        raise ConfigError(message("config.stealth-architecture", path=name))


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
    found = find_config(root, "trmv")
    if found is None:
        return None, None
    name = found.display()
    data = read_config(root, name)
    if found.stealth:
        stealth_refusal(data, name)
    return trmv_data(data, name), name


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
