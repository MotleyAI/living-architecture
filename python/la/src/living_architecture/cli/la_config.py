import argparse

from deterministic_refactor import config
from deterministic_refactor.config.command import command_argv, command_root, run_command


def _config(args: argparse.Namespace) -> int:
    root = command_root(args.root)
    return config.run_show(root) if args.subcommand == "show" else config.run_get(root, args.key)


def la_config(argv: list[str] | None = None) -> int:
    return run_command("la-config", command_argv(argv), _config)
