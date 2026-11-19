import argparse

from deterministic_refactor.config import run_get, run_show
from deterministic_refactor.config.command import command_argv, command_root
from living_architecture.config import la_view, run_command


def _config(args: argparse.Namespace) -> int:
    root = command_root(args.root)
    return run_show("la-config", root, la_view) if args.subcommand == "show" else run_get("la-config", root, args.key, la_view)


def la_config(argv: list[str] | None = None) -> int:
    return run_command("la-config", command_argv(argv), _config)
