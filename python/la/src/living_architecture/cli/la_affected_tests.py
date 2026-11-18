import argparse
from pathlib import Path

from deterministic_refactor.config.command import command_argv, run_command
from living_architecture import affected


def _affected_tests(args: argparse.Namespace) -> int:
    if args.language is not None:
        return affected.serve(args.language, cwd=Path.cwd())
    return affected.run(base=args.base, cwd=Path.cwd())


def la_affected_tests(argv: list[str] | None = None) -> int:
    return run_command("la-affected-tests", command_argv(argv), _affected_tests)
