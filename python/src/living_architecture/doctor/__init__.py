"""`la-doctor`: check the installed tools match the plugin and the repo config is valid."""

from __future__ import annotations

import shutil
from pathlib import Path

from living_architecture import __version__
from living_architecture.config import CONFIG_FILENAME, ConfigError, load_config
from living_architecture.contract import contract_hash, message

REQUIRED_EXECUTABLES = ("git", "gh")


def run_checks(*, root: Path, expect: str | None) -> list[str]:
    """Problems found; empty means healthy."""
    problems: list[str] = []
    if expect is not None and expect != __version__:
        problems.append(message("doctor.version-mismatch", installed=__version__, expected=expect))
    try:
        load_config(root)
    except ConfigError as exc:
        problems.append(str(exc))
    problems += [message("doctor.missing-executable", exe=exe) for exe in REQUIRED_EXECUTABLES if shutil.which(exe) is None]
    return problems


def run(*, root: Path, expect: str | None, print_hash: bool) -> int:
    if print_hash:
        print(contract_hash())
        return 0
    problems = run_checks(root=root, expect=expect)
    for problem in problems:
        print(message("doctor.fail", problem=problem))
    if not problems:
        source = CONFIG_FILENAME if (root / CONFIG_FILENAME).is_file() else message("doctor.no-config-file")
        print(message("doctor.ok", version=__version__, source=source))
    return 1 if problems else 0
