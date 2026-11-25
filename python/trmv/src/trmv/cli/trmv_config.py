import argparse

from trmv.config import run_get, run_show, trmv_view
from trmv.config.command import command_argv, command_root, run_command


def _config(args: argparse.Namespace) -> int:
    root = command_root(args.root)
    return run_show("trmv-config", root, trmv_view) if args.subcommand == "show" else run_get("trmv-config", root, args.key, trmv_view)


def trmv_config(argv: list[str] | None = None) -> int:
    return run_command("trmv-config", command_argv(argv), _config)
