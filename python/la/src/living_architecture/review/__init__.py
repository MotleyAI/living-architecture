"""Review shims: run a bundled contract script."""

from __future__ import annotations

import os
from typing import NoReturn

from living_architecture.contract import manifest, script_path


def run_shim(command: str, argv: list[str]) -> NoReturn:
    """Exec the command's bundled script with `argv` unchanged."""
    os.execvp("bash", ["bash", str(script_path(manifest()[command]["script"])), *argv])
