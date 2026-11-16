import argparse
from pathlib import Path

from living_architecture import config, conventions, twin
from living_architecture.cli import _argv, _run


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
    return _run("la-check-conventions", _argv(argv), _check_conventions)
