"""The release rule: a release whose tool inputs changed since the previous release raises the minor or major version."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

TOOL_PATHSPECS = (
    "shared",
    "conformance",
    "python/src",
    "node/src",
    "node/scripts",
    ":(glob)node/tsconfig*.json",
)
# Tool inputs compared with the package's own version substituted.
MANIFESTS = ("python/pyproject.toml", "python/uv.lock", "node/package.json", "node/package-lock.json")
_RELEASE = re.compile(r"([0-9]+)\.([0-9]+)\.([0-9]+)")


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
    for path in MANIFESTS:
        before = _show(root, previous, path)
        rebased = None if before is None else before.replace(previous.removeprefix("v"), version)
        if rebased != _show(root, "HEAD", path):
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
