import argparse

from deterministic_refactor.config import dr_view, run_get, run_show
from deterministic_refactor.config.command import command_argv, command_root, run_command


def _config(args: argparse.Namespace) -> int:
    root = command_root(args.root)
    return run_show("dr-config", root, dr_view) if args.subcommand == "show" else run_get("dr-config", root, args.key, dr_view)


def dr_config(argv: list[str] | None = None) -> int:
    return run_command("dr-config", command_argv(argv), _config)
