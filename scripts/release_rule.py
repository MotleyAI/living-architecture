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
    "python/dr/src",
    "python/la/src",
    "node/dr/src",
    "node/la/src",
    "node/scripts",
    "node/dr/scripts",
    "node/la/scripts",
    ":(glob)node/tsconfig*.json",
    ":(glob)node/*/tsconfig*.json",
)
PACKAGES = ("deterministic-refactor", "living-architecture")
DR = "deterministic-refactor"
_PYPI_PIN = re.compile(rf"^{DR}>=[^,]+,<\S+$")


def series(version: str) -> tuple[str, str]:
    """The `X.Y.0` base of `version`'s minor series and the next minor `X.(Y+1)`."""
    major, minor = version.split(".")[:2]
    return f"{major}.{minor}.0", f"{major}.{int(minor) + 1}"


def pypi_pin(version: str) -> str:
    base, upper = series(version)
    return f"{DR}>={base},<{upper}"


def tilde_pin(version: str) -> str:
    return f"~{series(version)[0]}"


def _set_pyproject(data: dict[str, Any], version: str) -> None:
    project = data.get("project")
    if project is None:
        return
    project["version"] = version
    project["dependencies"] = [pypi_pin(version) if _PYPI_PIN.match(d) else d for d in project.get("dependencies", [])]


def _set_uv_lock(data: dict[str, Any], version: str) -> None:
    for package in data["package"]:
        if package["name"] in PACKAGES:
            package["version"] = version


def _set_package_json(data: dict[str, Any], version: str) -> None:
    if "version" in data:
        data["version"] = version
    if DR in data.get("dependencies", {}):
        data["dependencies"][DR] = tilde_pin(version)


def _set_package_lock(data: dict[str, Any], version: str) -> None:
    if "version" in data:
        data["version"] = version
    for entry in data["packages"].values():
        if entry.get("name") in PACKAGES:
            _set_package_json(entry, version)


# Tool inputs compared as parsed data, with each package's own version fields and la's pin on dr set to the release's.
MANIFESTS: dict[str, tuple[Callable[[str], dict[str, Any]], Callable[[dict[str, Any], str], None]]] = {
    "python/pyproject.toml": (tomllib.loads, _set_pyproject),
    "python/dr/pyproject.toml": (tomllib.loads, _set_pyproject),
    "python/la/pyproject.toml": (tomllib.loads, _set_pyproject),
    "python/uv.lock": (tomllib.loads, _set_uv_lock),
    "node/package.json": (json.loads, _set_package_json),
    "node/dr/package.json": (json.loads, _set_package_json),
    "node/la/package.json": (json.loads, _set_package_json),
    "node/package-lock.json": (json.loads, _set_package_lock),
}
_RELEASE = re.compile(r"(\d+)\.(\d+)\.(\d+)", re.ASCII)
FORMATS_FILE = "shared/dr/config.yaml"
# Before the split, one formats list for living-architecture.yaml.
SINGLE_FORMATS_FILE = "shared/config.yaml"
SINGLE_FORMATS_CONFIG = "living-architecture.yaml"
_V = r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
_TAIL = r"[ \t]*(?:#.*)?"
_LIST = rf"\[({_V}(?:, {_V})*)?\]"
_FORMATS_KEY = "formats:"
_FORMATS = re.compile(rf"formats: {_LIST}{_TAIL}", re.ASCII)
_FORMAT = re.compile(rf"format: (?:({_V})|'({_V})'|\"({_V})\"){_TAIL}", re.ASCII)
_FILE_FORMATS = re.compile(rf"  ([\w.-]+): {_LIST}{_TAIL}", re.ASCII)


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


def _lines(text: str) -> list[str]:
    return [line.rstrip("\r") for line in text.split("\n")]


def parse_formats(text: str) -> list[str] | None:
    """The released formats of a pre-split `shared/config.yaml` text: its one-line `formats` list, else its single
    `format`; None when it declares neither in that form."""
    lines = _lines(text)
    for key, pattern in ((_FORMATS_KEY, _FORMATS), ("format:", _FORMAT)):
        found = [line for line in lines if line.startswith(key)]
        if found:
            match = pattern.fullmatch(found[0]) if len(found) == 1 else None
            if match is None:
                return None
            if key == "format:":
                return [next(group for group in match.groups() if group)]
            return match[1].split(", ") if match[1] else []
    return None


def parse_file_formats(text: str) -> dict[str, list[str]] | None:
    """The per-file released formats of a `shared/dr/config.yaml` text: its `formats:` block of one-line lists, one
    per file; None when it has no such block."""
    lines = _lines(text)
    starts = [i for i, line in enumerate(lines) if line.startswith(_FORMATS_KEY)]
    if len(starts) != 1 or lines[starts[0]].split("#")[0].strip() != _FORMATS_KEY:
        return None
    formats: dict[str, list[str]] = {}
    for line in lines[starts[0] + 1:]:
        if not line.startswith(" ") or not line.strip():
            break
        match = _FILE_FORMATS.fullmatch(line)
        if match is None or match[1] in formats:
            return None
        formats[match[1]] = match[2].split(", ") if match[2] else []
    return formats or None


def _exists(root: Path, rev: str, path: str) -> bool | None:
    """Whether `path` is in `rev`'s tree; None when git cannot tell."""
    listed = subprocess.run(["git", "ls-tree", "--name-only", rev, "--", path], cwd=root, capture_output=True,
                            text=True, check=False)
    return bool(listed.stdout) if listed.returncode == 0 else None


def _file_formats_at(root: Path, rev: str) -> dict[str, list[str]] | str:
    """The released formats per config file at `rev`, {} without a formats file; else why they cannot be read."""
    for path, parse in ((FORMATS_FILE, parse_file_formats), (SINGLE_FORMATS_FILE, parse_formats)):
        exists = _exists(root, rev, path)
        if exists is False:
            continue
        text = _show(root, rev, path) if exists else None
        parsed = None if text is None else parse(text)
        if parsed is None:
            return f"cannot read the released formats of {rev} from {path}"
        return parsed if isinstance(parsed, dict) else {SINGLE_FORMATS_CONFIG: parsed}
    return {}


def _listed(formats: list[str]) -> str:
    return f"[{', '.join(formats)}]"


def formats_problem(root: Path, version: str, previous: str) -> str | None:
    """Why some file's released formats at HEAD are neither `previous`'s nor those followed by exactly `version`."""
    before = _file_formats_at(root, previous)
    if isinstance(before, str):
        return before
    after = _file_formats_at(root, "HEAD")
    if isinstance(after, str):
        return after
    problems = [
        f"the released formats of {name} changed from {_listed(old)} at {previous} to {_listed(new)}; a release may"
        f" only append its own version {version}"
        for name in sorted({*before, *after})
        if (new := after.get(name, [])) not in ((old := before.get(name, [])), [*old, version])
    ]
    return "; ".join(problems) or None


def changed_tool_inputs(root: Path, version: str, previous: str) -> list[str]:
    """Tool inputs that differ between `previous` and HEAD, manifests beyond their own versions and la's pin."""
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
