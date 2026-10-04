"""basedpyright as la-typecheck's Python checker: its baseline flag and exit codes."""

from __future__ import annotations

BASEDPYRIGHT_WRITE_FLAG = "--writebaseline"


def basedpyright_exit(code: int, *, write: bool) -> int:
    """0 and 1 pass through (write mode: both mean written, so 0); anything else, a signal included, is 2."""
    if code in (0, 1):
        return 0 if write else code
    return 2


def empty_basedpyright_baseline() -> str:
    """The baseline of a clean project, which basedpyright itself does not write."""
    return '{\n  "files": {}\n}\n'
