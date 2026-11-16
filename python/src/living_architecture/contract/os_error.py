"""OS errors rendered from the shared os.* templates, and the one existence probe."""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path

from living_architecture.contract.render import message

_REASONS = {
    "ENOENT": "os.not-found",
    "EACCES": "os.permission-denied",
    "EISDIR": "os.is-a-directory",
    "ENOTDIR": "os.not-a-directory",
}


def os_error_reason(error: OSError) -> str:
    """The reason alone, chosen by the error's symbolic code."""
    code = errno.errorcode.get(error.errno) if isinstance(error.errno, int) else None
    if code in _REASONS:
        return message(_REASONS[code])
    return message("os.other", code=code or "unknown")


def display_path(path: str | os.PathLike[str], root: str | os.PathLike[str]) -> str:
    """`path` relative to `root` with `/` separators when lexically under it, else absolute."""
    full, base = os.path.abspath(path), os.path.abspath(root)
    if full == base:
        return "."
    try:
        under = os.path.commonpath([full, base]) == base
    except ValueError:  # different drives
        under = False
    return Path(os.path.relpath(full, base)).as_posix() if under else full


def os_error_text(error: OSError, root: str | os.PathLike[str], path: str | os.PathLike[str] | None = None) -> str:
    """`{path}: {reason}` for the site's path, else the error's own; the reason alone when there is neither."""
    shown = path if path is not None else error.filename if isinstance(error.filename, str) else None
    reason = os_error_reason(error)
    if shown is None:
        return reason
    return message("os.error", path=display_path(shown, root), reason=reason)


def is_regular_file(path: str | os.PathLike[str]) -> bool:
    """True for a regular file, False when missing or not regular; any other stat error propagates."""
    try:
        return stat.S_ISREG(os.stat(path).st_mode)
    except FileNotFoundError:
        return False
