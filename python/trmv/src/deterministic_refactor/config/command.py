"""Running a command: parse argv per its manifest, check the config file, dispatch to the handler."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from deterministic_refactor import config
from deterministic_refactor.contract import manifest
from deterministic_refactor.contract.parser import parse


def run_command(
    command: str,
    argv: list[str],
    handler: Callable[[argparse.Namespace], int],
    commands: dict[str, Any] | None = None,
    config_file: str | None = None,
) -> int:
    """Parse `argv` per `commands` (default: dr's manifest; not for a passthrough command), refuse both config files
    and check the format of `config_file` (default: the one dr reads) unless exempt, then run `handler`."""
    spec = (commands or manifest())[command]
    args = argparse.Namespace() if spec.get("passthrough") else parse(command, argv, commands)
    if spec.get("format") != "exempt":
        root = _checked_root(args)
        problem = config.both_files_problem(root) or config.check_format(root, config_file)
        if problem is not None:
            print(problem, file=sys.stderr)
            return 2
    return handler(args)


def _checked_root(args: argparse.Namespace) -> Path:
    """The repo whose format a command checks: `--root`, else the git root of `--project`, else of the cwd."""
    root: str | None = getattr(args, "root", None)
    project: str | None = getattr(args, "project", None)
    return command_root(root) if root or not project else config.find_repo_root(Path(project))


def command_root(root: str | None) -> Path:
    return Path(root).resolve() if root else config.find_repo_root(Path.cwd())


def command_argv(argv: list[str] | None) -> list[str]:
    return list(sys.argv[1:] if argv is None else argv)
