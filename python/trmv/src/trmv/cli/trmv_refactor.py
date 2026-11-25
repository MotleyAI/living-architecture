import argparse

from trmv import refactor
from trmv.config.command import command_argv, run_command


def _refactor(raw: list[str], args: argparse.Namespace) -> int:
    return refactor.route_refactor(
        raw,
        args,
        lambda: refactor.run_refactor(project_root=args.project, command=args.subcommand, apply=args.apply, options=vars(args)),
    )


def trmv_refactor(argv: list[str] | None = None) -> int:
    raw = command_argv(argv)
    return run_command("trmv-refactor", raw, lambda args: _refactor(raw, args))
