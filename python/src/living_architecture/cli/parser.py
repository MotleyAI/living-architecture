"""argparse parsers built from the shared CLI manifest (no abbreviations, `--` honoured, usage → exit 2)."""

from __future__ import annotations

import argparse
from typing import Any

from living_architecture.contract import manifest

_TYPES: dict[str, type] = {"string": str, "path": str, "int": int, "float": float}


def _dest(option: dict[str, Any]) -> str:
    return option.get("dest", option["name"].lstrip("-").replace("-", "_"))


def _add_arguments(parser: argparse.ArgumentParser, spec: dict[str, Any]) -> None:
    for positional in spec.get("positionals", []):
        kwargs: dict[str, Any] = {"help": positional["help"]}
        if "nargs" in positional:
            kwargs["nargs"] = positional["nargs"]
        parser.add_argument(positional["name"], **kwargs)
    for option in spec.get("options", []):
        kwargs = {"dest": _dest(option), "help": option["help"]}
        if option["type"] == "flag":
            kwargs["action"] = "store_true" if option.get("store", True) else "store_false"
        else:
            kwargs["type"] = _TYPES[option["type"]]
            for key in ("metavar", "choices", "default", "required"):
                if key in option:
                    kwargs[key] = option[key]
            if option.get("repeatable"):
                kwargs.update(action="append", default=[])
        parser.add_argument(option["name"], **kwargs)


def build_parser(command: str) -> argparse.ArgumentParser:
    spec = manifest()[command]
    parser = argparse.ArgumentParser(prog=command, description=spec["help"], allow_abbrev=False)
    _add_arguments(parser, spec)
    subcommands = spec.get("subcommands", {})
    if subcommands:
        sub = parser.add_subparsers(dest="subcommand", required=True)
        for name, sub_spec in subcommands.items():
            sub_parser = sub.add_parser(name, help=sub_spec["help"], description=sub_spec["help"], allow_abbrev=False)
            _add_arguments(sub_parser, sub_spec)
    return parser


def _subcommand_after_double_dash(argv: list[str], subcommands: dict[str, Any]) -> list[str]:
    """`-- SUB ARGS` → `SUB -- ARGS`, so `--` ends options in the subcommand on every Python version."""
    if not subcommands or "--" not in argv:
        return argv
    i = argv.index("--")
    if i + 1 >= len(argv) or any(token in subcommands for token in argv[:i]):
        return argv
    return [*argv[:i], argv[i + 1], "--", *argv[i + 2 :]]


def parse(command: str, argv: list[str]) -> argparse.Namespace:
    """Parse `argv` for `command`; a usage error exits 2."""
    spec = manifest()[command]
    parser = build_parser(command)
    args = parser.parse_args(_subcommand_after_double_dash(argv, spec.get("subcommands", {})))
    required = spec.get("require_one_of")
    if required and not any(getattr(args, dest) for dest in required):
        parser.error(f"one of {', '.join(required)} is required")
    return args
