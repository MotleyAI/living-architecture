import argparse

from deterministic_refactor import refactor
from deterministic_refactor.config.command import command_argv, run_command


def _refactor(raw: list[str], args: argparse.Namespace) -> int:
    return refactor.route_refactor(
        raw,
        args,
        lambda: refactor.run_refactor(project_root=args.project, command=args.subcommand, apply=args.apply, options=vars(args)),
    )


def dr_refactor(argv: list[str] | None = None) -> int:
    raw = command_argv(argv)
    return run_command("dr-refactor", raw, lambda args: _refactor(raw, args))
