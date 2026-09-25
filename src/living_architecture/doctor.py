"""`la-doctor`: check the installed tools match the plugin and the repo config is valid."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from living_architecture import __version__
from living_architecture.config import CONFIG_FILENAME, ConfigError, find_repo_root, load_config

REQUIRED_EXECUTABLES = ("git", "gh")


def run_checks(*, root: Path, expect: str | None) -> list[str]:
    """Problems found; empty means healthy."""
    problems: list[str] = []
    if expect is not None and expect != __version__:
        problems.append(
            f"installed la tools are {__version__} but the plugin expects {expect}; "
            "reinstall the tools from the same checkout/tag as the plugin"
        )
    try:
        load_config(root)
    except ConfigError as exc:
        problems.append(str(exc))
    problems += [f"`{exe}` not found on PATH" for exe in REQUIRED_EXECUTABLES if shutil.which(exe) is None]
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="la-doctor", description=__doc__)
    parser.add_argument("--expect", help="plugin version the calling skill was written for")
    parser.add_argument("--root", type=Path, help="repo root (default: nearest git root of cwd)")
    args = parser.parse_args(argv)
    root = args.root.resolve() if args.root else find_repo_root(Path.cwd())
    problems = run_checks(root=root, expect=args.expect)
    for problem in problems:
        print(f"FAIL: {problem}")
    if not problems:
        source = CONFIG_FILENAME if (root / CONFIG_FILENAME).is_file() else "defaults (no config file)"
        print(f"ok: la tools {__version__}; config from {source}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
