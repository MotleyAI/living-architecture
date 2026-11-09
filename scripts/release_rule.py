"""The release rule: a release whose tool inputs changed since the previous release raises the minor or major version."""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any

TOOL_PATHSPECS = (
    "shared",
    "conformance",
    "python/src",
    "node/src",
    "node/scripts",
    ":(glob)node/tsconfig*.json",
)
PACKAGE = "living-architecture"


def _set_pyproject(data: dict[str, Any], version: str) -> None:
    data["project"]["version"] = version


def _set_uv_lock(data: dict[str, Any], version: str) -> None:
    for package in data["package"]:
        if package["name"] == PACKAGE:
            package["version"] = version


def _set_package_json(data: dict[str, Any], version: str) -> None:
    data["version"] = version


def _set_package_lock(data: dict[str, Any], version: str) -> None:
    data["version"] = data["packages"][""]["version"] = version


# Tool inputs compared as parsed data, with the package's own version fields set to the release's.
MANIFESTS: dict[str, tuple[Callable[[str], dict[str, Any]], Callable[[dict[str, Any], str], None]]] = {
    "python/pyproject.toml": (tomllib.loads, _set_pyproject),
    "python/uv.lock": (tomllib.loads, _set_uv_lock),
    "node/package.json": (json.loads, _set_package_json),
    "node/package-lock.json": (json.loads, _set_package_lock),
}
_RELEASE = re.compile(r"(\d+)\.(\d+)\.(\d+)", re.ASCII)


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout


def _parse(version: str) -> tuple[int, int, int] | None:
    match = _RELEASE.fullmatch(version)
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


def previous_release(root: Path, version: str) -> str | None:
    """The highest `vX.Y.Z` tag reachable from HEAD below `version`, or None."""
    current = _parse(version)
    if current is None:
        return None
    below = [
        (parsed, tag)
        for tag in git(root, "tag", "--merged", "HEAD", "--list", "v*").split()
        if (parsed := _parse(tag.removeprefix("v"))) is not None and parsed < current
    ]
    return max(below)[1] if below else None


def _show(root: Path, rev: str, path: str) -> str | None:
    shown = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=root, capture_output=True, text=True, check=False)
    return shown.stdout if shown.returncode == 0 else None


def changed_tool_inputs(root: Path, version: str, previous: str) -> list[str]:
    """Tool inputs that differ between `previous` and HEAD, manifests beyond their own version."""
    listed = git(root, "diff", "--name-only", "--no-renames", "-z", previous, "HEAD", "--", *TOOL_PATHSPECS)
    changed = [path for path in listed.split("\0") if path]
    for path, (parse, set_version) in MANIFESTS.items():
        before, after = _show(root, previous, path), _show(root, "HEAD", path)
        rebased = None if before is None else parse(before)
        if rebased is not None:
            set_version(rebased, version)
        if rebased != (None if after is None else parse(after)):
            changed.append(path)
    return sorted(changed)


def bump_problem(root: Path, version: str, previous: str) -> str | None:
    """Why releasing HEAD as `version` after the tag `previous` breaks the rule, or None."""
    current, last = _parse(version), _parse(previous.removeprefix("v"))
    if current is None or last is None:
        return f"{version} is not of the form X.Y.Z"
    if current[:2] > last[:2]:
        return None
    changed = changed_tool_inputs(root, version, previous)
    if not changed:
        return None
    return f"tool inputs changed since {previous}, so {version} must raise the minor or major version: {', '.join(changed)}"
