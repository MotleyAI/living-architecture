import argparse

from living_architecture import refactor
from living_architecture.cli import _argv, _run


def _refactor(raw: list[str], args: argparse.Namespace) -> int:
    return refactor.route_refactor(
        raw,
        args,
        lambda: refactor.run_refactor(project_root=args.project, command=args.subcommand, apply=args.apply, options=vars(args)),
    )


def dr_refactor(argv: list[str] | None = None) -> int:
    raw = _argv(argv)
    return _run("dr-refactor", raw, lambda args: _refactor(raw, args))
