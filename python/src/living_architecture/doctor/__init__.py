"""`la-doctor`: check the installed tools match the plugin and the repo config is valid."""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from living_architecture import __version__
from living_architecture.config import CONFIG_FILENAME, ConfigError, load_config
from living_architecture.contract import contract_hash, message

REQUIRED_EXECUTABLES = ("git", "gh")
PLUGIN_MANIFEST = Path(".claude-plugin") / "plugin.json"
_LONE_SURROGATE = re.compile("[\ud800-\udfff]")


def _version_problem(expected: str) -> str | None:
    if expected == __version__:
        return None
    return message("doctor.version-mismatch", installed=__version__, expected=expected)


def _reject_constant(name: str) -> None:
    raise ValueError(name)


def _plugin_problem(plugin: str) -> str | None:
    """Check against the version in the nearest `.claude-plugin/plugin.json` at or above `plugin`."""
    # Collapse POSIX's leading `//` as Node's resolve() does.
    start = Path(re.sub(r"^//(?=[^/])", "/", os.path.abspath(plugin)))
    manifest = next((d / PLUGIN_MANIFEST for d in (start, *start.parents) if (d / PLUGIN_MANIFEST).is_file()), None)
    if manifest is None:
        return message("doctor.plugin-not-found", dir=start)
    try:
        data = json.loads(manifest.read_bytes().decode("utf-8"), parse_constant=_reject_constant)
    except (OSError, ValueError):
        data = None
    version = data.get("version") if isinstance(data, dict) else None
    if not isinstance(version, str) or _LONE_SURROGATE.search(version):
        return message("doctor.plugin-invalid", path=manifest)
    return _version_problem(version)


def run_checks(*, root: Path, expect: str | None, plugin: str | None = None) -> list[str]:
    """Problems found; empty means healthy."""
    versions = (
        _version_problem(expect) if expect is not None else None,
        _plugin_problem(plugin) if plugin is not None else None,
    )
    problems = [problem for problem in versions if problem is not None]
    try:
        load_config(root)
    except ConfigError as exc:
        problems.append(str(exc))
    problems += [message("doctor.missing-executable", exe=exe) for exe in REQUIRED_EXECUTABLES if shutil.which(exe) is None]
    return problems


def run(*, root: Path, expect: str | None, plugin: str | None, print_hash: bool) -> int:
    if print_hash:
        print(contract_hash())
        return 0
    problems = run_checks(root=root, expect=expect, plugin=plugin)
    for problem in problems:
        print(message("doctor.fail", problem=problem))
    if not problems:
        source = CONFIG_FILENAME if (root / CONFIG_FILENAME).is_file() else message("doctor.no-config-file")
        print(message("doctor.ok", version=__version__, source=source))
    return 1 if problems else 0
