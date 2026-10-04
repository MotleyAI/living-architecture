"""`la-doctor`: check the installed tools match the plugin and the repo config is valid."""

from __future__ import annotations

import shutil
from pathlib import Path

from living_architecture import __version__
from living_architecture.config import CONFIG_FILENAME, ConfigError, LaConfig, load_config
from living_architecture.contract import contract_hash, message

REQUIRED_EXECUTABLES = ("git", "gh")


def _consistency(root: Path, cfg: LaConfig) -> list[str]:
    """The config's gate decisions that the disk contradicts, in a fixed order."""
    problems: list[str] = []
    has_openspec = (root / "openspec").is_dir()
    has_architecture = (root / "architecture" / "index.yaml").is_file()
    if cfg.openspec != has_openspec:
        problems.append(message("doctor.openspec-absent" if cfg.openspec else "doctor.openspec-present"))
    if cfg.architecture != has_architecture:
        problems.append(message("doctor.architecture-absent" if cfg.architecture else "doctor.architecture-present"))
    if cfg.tracker == "none" and not cfg.openspec:
        problems.append(message("doctor.no-plan-store"))
    return problems


def _config_problems(root: Path, *, require_config: bool) -> list[str]:
    if not (root / CONFIG_FILENAME).is_file():
        return [message("doctor.config-missing")] if require_config else []
    try:
        cfg = load_config(root)
    except ConfigError as exc:
        return [str(exc)]
    return _consistency(root, cfg)


def run_checks(*, root: Path, expect: str | None, require_config: bool = False) -> list[str]:
    """Problems found; empty means healthy. Config-vs-disk checks run only when the config file exists."""
    problems: list[str] = []
    if expect is not None and expect != __version__:
        problems.append(message("doctor.version-mismatch", installed=__version__, expected=expect))
    problems += _config_problems(root, require_config=require_config)
    problems += [message("doctor.missing-executable", exe=exe) for exe in REQUIRED_EXECUTABLES if shutil.which(exe) is None]
    return problems


def run(*, root: Path, expect: str | None, print_hash: bool, require_config: bool = False) -> int:
    if print_hash:
        print(contract_hash())
        return 0
    problems = run_checks(root=root, expect=expect, require_config=require_config)
    for problem in problems:
        print(message("doctor.fail", problem=problem))
    if not problems:
        source = CONFIG_FILENAME if (root / CONFIG_FILENAME).is_file() else message("doctor.no-config-file")
        print(message("doctor.ok", version=__version__, source=source))
    return 1 if problems else 0
