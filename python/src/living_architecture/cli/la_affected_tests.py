import argparse
from pathlib import Path

from living_architecture import affected
from living_architecture.cli import _argv, _run


def _affected_tests(args: argparse.Namespace) -> int:
    if args.language is not None:
        return affected.serve(args.language, cwd=Path.cwd())
    return affected.run(base=args.base, cwd=Path.cwd())


def la_affected_tests(argv: list[str] | None = None) -> int:
    return _run("la-affected-tests", _argv(argv), _affected_tests)
