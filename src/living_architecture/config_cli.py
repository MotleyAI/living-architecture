"""`la-config`: print resolved config values for skills and scripts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from living_architecture.config import ConfigError, find_repo_root, load_config


def _lookup(data: Any, dotted: str) -> Any:
    node = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(dotted)
        node = node[part]
    return node


def format_value(value: Any) -> str:
    """Shell-friendly: bools lowercase, None empty, containers as JSON."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="la-config", description=__doc__)
    parser.add_argument("--root", type=Path, help="repo root (default: nearest git root of cwd)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    get = sub.add_parser("get", help="print one value by dotted key, e.g. reviewers.sonar.enabled")
    get.add_argument("key")
    sub.add_parser("show", help="print the whole resolved config as JSON")
    args = parser.parse_args(argv)

    root = args.root.resolve() if args.root else find_repo_root(Path.cwd())
    try:
        data = load_config(root).model_dump()
    except ConfigError as exc:
        print(f"la-config: {exc}", file=sys.stderr)
        return 1
    if args.cmd == "show":
        print(json.dumps(data, indent=2))
        return 0
    try:
        print(format_value(_lookup(data, args.key)))
    except KeyError:
        print(f"la-config: unknown key {args.key!r}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
