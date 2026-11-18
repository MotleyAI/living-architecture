import argparse

from living_architecture import config
from living_architecture.cli import _argv, _root, _run


def _config(args: argparse.Namespace) -> int:
    root = _root(args.root)
    return config.run_show(root) if args.subcommand == "show" else config.run_get(root, args.key)


def la_config(argv: list[str] | None = None) -> int:
    return _run("la-config", _argv(argv), _config)
