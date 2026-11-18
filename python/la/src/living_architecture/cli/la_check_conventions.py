import argparse
from pathlib import Path

from deterministic_refactor import config, twin
from deterministic_refactor.config.command import command_argv, run_command
from living_architecture import conventions


def _check_conventions(args: argparse.Namespace) -> int:
    if args.emit:
        return conventions.emit(args.language or twin.NATIVE_LANGUAGE, cwd=Path.cwd())
    return conventions.check_conventions(
        repo_root=config.find_repo_root(Path.cwd()),
        pr=args.pr,
        repo=args.repo,
        base=args.base,
        files=args.files,
        excludes=args.exclude,
        cap_pct=args.text_ratio_cap,
    )


def la_check_conventions(argv: list[str] | None = None) -> int:
    return run_command("la-check-conventions", command_argv(argv), _check_conventions)
