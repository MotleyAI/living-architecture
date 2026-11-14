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
FORMATS_FILE = "shared/config.yaml"
_V = r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
_TAIL = r"[ \t]*(?:#.*)?"
_FORMATS = re.compile(rf"formats: \[({_V}(?:, {_V})*)?\]{_TAIL}", re.ASCII)
_FORMAT = re.compile(rf"format: (?:({_V})|'({_V})'|\"({_V})\"){_TAIL}", re.ASCII)


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


def parse_formats(text: str) -> list[str] | None:
    """The released formats of a `shared/config.yaml` text: its one-line `formats` list, else its single `format`;
    None when it declares neither in that form."""
    lines = [line.rstrip("\r") for line in text.split("\n")]
    for key, pattern in (("formats:", _FORMATS), ("format:", _FORMAT)):
        found = [line for line in lines if line.startswith(key)]
        if found:
            match = pattern.fullmatch(found[0]) if len(found) == 1 else None
            if match is None:
                return None
            if key == "format:":
                return [next(group for group in match.groups() if group)]
            return match[1].split(", ") if match[1] else []
    return None


def _formats_at(root: Path, rev: str) -> list[str] | str:
    """The released formats at `rev`, [] without the file there; else why they cannot be read."""
    listed = subprocess.run(
        ["git", "ls-tree", "--name-only", rev, "--", FORMATS_FILE], cwd=root, capture_output=True, text=True, check=False
    )
    if listed.returncode == 0 and not listed.stdout:
        return []
    shown = subprocess.run(["git", "show", f"{rev}:{FORMATS_FILE}"], cwd=root, capture_output=True, text=True, check=False)
    formats = parse_formats(shown.stdout) if listed.returncode == shown.returncode == 0 else None
    return f"cannot read the released formats of {rev} from {FORMATS_FILE}" if formats is None else formats


def _listed(formats: list[str]) -> str:
    return f"[{', '.join(formats)}]"


def formats_problem(root: Path, version: str, previous: str) -> str | None:
    """Why HEAD's released formats are neither `previous`'s nor those followed by exactly `version`, or None."""
    before = _formats_at(root, previous)
    if isinstance(before, str):
        return before
    after = _formats_at(root, "HEAD")
    if isinstance(after, str):
        return after
    if after in (before, [*before, version]):
        return None
    return (
        f"the released formats changed from {_listed(before)} at {previous} to {_listed(after)}; a release may only"
        f" append its own version {version}"
    )


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
    problems = [problem] if (problem := formats_problem(root, version, previous)) is not None else []
    changed = [] if current[:2] > last[:2] else changed_tool_inputs(root, version, previous)
    if changed:
        problems.append(
            f"tool inputs changed since {previous}, so {version} must raise the minor or major version: {', '.join(changed)}"
        )
    return "; ".join(problems) or None
