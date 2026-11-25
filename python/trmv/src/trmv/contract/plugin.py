"""A doctor's `--plugin DIR`: the calling plugin's version against the installed tools' minor series."""

from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Callable
from pathlib import Path

from trmv.contract.render import message

PLUGIN_MANIFEST = Path(".claude-plugin") / "plugin.json"
_LONE_SURROGATE = re.compile("[\ud800-\udfff]")
_VERSION_FORM = re.compile(r"(\d+)\.(\d+)\..+", re.ASCII | re.DOTALL)


def _series(version: str) -> tuple[str, str] | None:
    """Major and minor of `<digits>.<digits>.<rest>` as written, or None."""
    match = _VERSION_FORM.fullmatch(version)
    return (match[1], match[2]) if match else None


def _canonical(series: tuple[str, str]) -> tuple[str, ...]:
    return tuple(part.lstrip("0") or "0" for part in series)


def _reject_constant(name: str) -> None:
    raise ValueError(name)


def _is_file(path: Path) -> bool:
    """A missing entry or a path under a regular file is absent; other stat errors propagate."""
    try:
        return stat.S_ISREG(path.stat().st_mode)
    except (FileNotFoundError, NotADirectoryError):
        return False


class _Tools:
    """The installed tools a doctor checks: their package's short name, version and install command at a version."""

    def __init__(self, name: str, version: str, install: Callable[[str], str]) -> None:
        self.name = name
        self.version = version
        self.install = install

    def problem(self, expected: str, series: tuple[str, str]) -> str | None:
        installed = _series(self.version)
        if installed is not None and _canonical(installed) == _canonical(series):
            return None
        return message(
            "doctor.version-mismatch",
            package=self.name,
            installed=self.version,
            expected=expected,
            series=".".join(series),
            install=self.install(expected),
        )


def _manifest_problem(manifest: Path, raw: bytes, tools: _Tools) -> str | None:
    try:
        data = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except ValueError:
        data = None
    version = data.get("version") if isinstance(data, dict) else None
    if not isinstance(version, str) or _LONE_SURROGATE.search(version) or (series := _series(version)) is None:
        return message("doctor.plugin-invalid", path=manifest)
    return tools.problem(version, series)


def plugin_problem(plugin: str, name: str, version: str, install: Callable[[str], str]) -> str | None:
    """The tools `name` at `version` against the nearest `.claude-plugin/plugin.json` at or above `plugin`, or None
    when they share its minor series; `install(v)` is the command installing the tools at `v`."""
    tools = _Tools(name, version, install)
    # Collapse POSIX's leading `//` as Node's resolve() does.
    start = Path(re.sub(r"^//(?=[^/])", "/", os.path.abspath(plugin)))
    for directory in (start, *start.parents):
        manifest = directory / PLUGIN_MANIFEST
        try:
            if not _is_file(manifest):
                continue
            raw = manifest.read_bytes()
        except OSError:
            return message("doctor.plugin-unreadable", path=manifest)
        return _manifest_problem(manifest, raw, tools)
    return message("doctor.plugin-not-found", dir=start)
