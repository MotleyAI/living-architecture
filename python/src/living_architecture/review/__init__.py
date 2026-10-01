"""Review shims: run a bundled contract script, gated by the repo config."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import NoReturn

from living_architecture.config import ConfigError, LaConfig, find_repo_root, load_config
from living_architecture.contract import manifest, message, script_path


def _config(prog: str) -> LaConfig:
    try:
        return load_config(find_repo_root(Path.cwd()))
    except ConfigError as exc:
        print(message("review.config-error", prog=prog, error=str(exc)), file=sys.stderr)
        raise SystemExit(2) from exc


def run_shim(command: str, argv: list[str]) -> NoReturn:
    """Exec the command's bundled script with `argv`, after its config gate (cli.yaml `gate`)."""
    spec = manifest()[command]
    args = list(argv)
    gate = spec.get("gate")
    if gate == "coderabbit" and not _config(command).reviewers.coderabbit:
        print(message("review.coderabbit-disabled", prog=command), file=sys.stderr)
        raise SystemExit(3)
    if gate == "skip-coderabbit" and not _config(command).reviewers.coderabbit:
        args.append("--skip-coderabbit")
    os.execvp("bash", ["bash", str(script_path(spec["script"])), *args])
