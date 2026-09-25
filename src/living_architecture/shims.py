"""`la-*` entry points for the bundled bash scripts, gated by the repo config."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import NoReturn

from living_architecture.config import ConfigError, LaConfig, find_repo_root, load_config

SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"


def _exec(script: str, argv: list[str]) -> NoReturn:
    os.execvp("bash", ["bash", str(SCRIPTS_DIR / script), *argv])


def _config(prog: str) -> LaConfig:
    try:
        return load_config(find_repo_root(Path.cwd()))
    except ConfigError as exc:
        print(f"{prog}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def _require_coderabbit(prog: str) -> None:
    if not _config(prog).reviewers.coderabbit:
        print(
            f"{prog}: CodeRabbit is disabled for this repo (set reviewers.coderabbit: true in"
            " living-architecture.yaml to enable it)",
            file=sys.stderr,
        )
        raise SystemExit(3)


def _args(argv: list[str] | None) -> list[str]:
    return list(sys.argv[1:] if argv is None else argv)


def fetch_coderabbit_threads(argv: list[str] | None = None) -> NoReturn:
    _require_coderabbit("la-fetch-coderabbit-threads")
    _exec("fetch-coderabbit-threads.sh", _args(argv))


def reply_invalid_coderabbit(argv: list[str] | None = None) -> NoReturn:
    _require_coderabbit("la-reply-invalid-coderabbit")
    _exec("reply-invalid-coderabbit.sh", _args(argv))


def reply_to_pr_thread(argv: list[str] | None = None) -> NoReturn:
    _exec("reply-to-pr-thread.sh", _args(argv))


def fetch_failed_pr_checks(argv: list[str] | None = None) -> NoReturn:
    _exec("fetch-failed-pr-checks.sh", _args(argv))


def wait_for_reviews(argv: list[str] | None = None) -> NoReturn:
    args = _args(argv)
    if not _config("la-wait-for-reviews").reviewers.coderabbit:
        args.append("--skip-coderabbit")
    _exec("wait-for-reviews.sh", args)
