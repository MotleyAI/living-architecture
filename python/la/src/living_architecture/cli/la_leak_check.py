import argparse

from living_architecture import leaks
from living_architecture.config import run_command
from trmv.config.command import command_argv, command_root


def _leak_check(args: argparse.Namespace) -> int:
    return leaks.run(base=args.base, root=command_root(None))


def la_leak_check(argv: list[str] | None = None) -> int:
    return run_command("la-leak-check", command_argv(argv), _leak_check)
