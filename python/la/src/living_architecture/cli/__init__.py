"""What every command's entry module (`cli/<command>.py`) shares: parse argv per the shared manifest, check the repo
format, dispatch to the handler."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from living_architecture import config
from living_architecture.cli.parser import parse
from living_architecture.contract import manifest


def _argv(argv: list[str] | None) -> list[str]:
    return list(sys.argv[1:] if argv is None else argv)


def _root(root: str | None) -> Path:
    return Path(root).resolve() if root else config.find_repo_root(Path.cwd())


def _checked_root(args: argparse.Namespace) -> Path:
    """The repo whose format a command checks: `--root`, else the git root of `--project`, else of the cwd."""
    root: str | None = getattr(args, "root", None)
    project: str | None = getattr(args, "project", None)
    return _root(root) if root or not project else config.find_repo_root(Path(project))


def _run(command: str, argv: list[str], handler: Callable[[argparse.Namespace], int]) -> int:
    """Parse `argv` (not for a passthrough command), check the repo format unless exempt, then run `handler`."""
    spec = manifest()[command]
    args = argparse.Namespace() if spec.get("passthrough") else parse(command, argv)
    if spec.get("format") != "exempt":
        problem = config.check_format(_checked_root(args))
        if problem is not None:
            print(problem, file=sys.stderr)
            return 2
    return handler(args)
