"""`dr-doctor`: check the installed dr tools match the plugin's minor series and the config dr reads is valid."""

from __future__ import annotations

import shutil
from pathlib import Path

from deterministic_refactor import NATIVE_LANGUAGE, __version__, twin
from deterministic_refactor.config import (
    ConfigError,
    both_files_problem,
    check_format,
    config_source,
    load_with_languages,
    repo_languages,
)
from deterministic_refactor.contract import DR, contract_hash, language, message, plugin_problem

REQUIRED_EXECUTABLES = ("git",)


def _install(version: str) -> str:
    return twin.install_command(NATIVE_LANGUAGE, twin.dr_identity(), version)


def _config_problems(root: Path, *, require_config: bool) -> tuple[list[str], list[str]]:
    """The problems of the config dr reads, and the executables its repo languages need."""
    refusal = check_format(root)
    if refusal is not None:
        return [refusal], []
    problems = [message("doctor.dr-config-missing")] if require_config and config_source(root) is None else []
    try:
        _, settings = load_with_languages(root)
    except ConfigError as exc:
        return [*problems, str(exc)], []
    if not (root / ".git").exists():
        return problems, []
    try:
        languages = repo_languages(root, settings)
    except ConfigError as exc:
        return [*problems, str(exc)], []
    return problems, [exe for lang_id in languages for exe in language(lang_id)["executables"]]


def run_checks(*, root: Path, plugin: str | None = None, require_config: bool = False) -> list[str]:
    """Problems found; empty means healthy. Both config files present replace every check that reads the config."""
    problems: list[str] = []
    if plugin is not None and (version := plugin_problem(plugin, DR.yaml("cli.yaml")["plugin"], __version__, _install)):
        problems.append(version)
    executables = list(REQUIRED_EXECUTABLES)
    both = both_files_problem(root)
    if both is not None:
        problems.append(both)
    else:
        config_problems, needed = _config_problems(root, require_config=require_config)
        problems += config_problems
        executables += needed
    problems += [message("doctor.missing-executable", exe=exe) for exe in executables if shutil.which(exe) is None]
    return problems


def run(*, root: Path, plugin: str | None, print_hash: bool, require_config: bool = False) -> int:
    if print_hash:
        print(contract_hash())
        return 0
    problems = run_checks(root=root, plugin=plugin, require_config=require_config)
    for problem in problems:
        print(message("doctor.fail", problem=problem))
    if not problems:
        source = config_source(root) or message("doctor.no-config-file")
        print(message("doctor.ok", package=DR.yaml("cli.yaml")["plugin"], version=__version__, source=source))
    return 1 if problems else 0
