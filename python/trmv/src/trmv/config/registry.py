"""The stealth path registries: which of a package's paths show in a stealth repo's working tree."""

from __future__ import annotations

import subprocess
from pathlib import Path

from trmv.config.load import ConfigError, present_files
from trmv.contract import message, stealth_registry


def _listed(root: Path, args: list[str]) -> set[str]:
    try:
        proc = subprocess.run(["git", *args], cwd=root, capture_output=True, check=False)
    except OSError as exc:
        raise ConfigError(message("changes.git-failed", args=" ".join(args))) from exc
    if proc.returncode != 0:
        raise ConfigError(message("changes.git-failed", args=" ".join(args)))
    return {p.decode("utf-8", "surrogateescape") for p in proc.stdout.split(b"\0") if p}


def stray_paths(root: Path, paths: list[str], prefixes: list[str] | None = None) -> list[tuple[str, bool]]:
    """Each of `paths`, then each path under one of `prefixes`, that is staged as an addition or present, untracked and
    not ignored, in that order (a prefix's paths in code-point order), with whether it is staged."""
    staged = _listed(root, ["diff", "--cached", "--name-only", "--diff-filter=A", "-z"])
    untracked = _listed(root, ["ls-files", "-z", "--others", "--exclude-standard"])
    shown = staged | untracked
    found = [p for p in paths if p in shown]
    for prefix in prefixes or []:
        found += sorted(p for p in shown if p.startswith(prefix) and p not in found)
    return [(p, p in staged) for p in found]


def stray_findings(root: Path, paths: list[str], prefixes: list[str] | None = None) -> list[str]:
    """The doctors' findings for `stray_paths`."""
    return [message("doctor.stealth-staged" if staged else "doctor.stealth-untracked", path=p)
            for p, staged in stray_paths(root, paths, prefixes)]


def trmv_stray_findings(root: Path) -> list[str]:
    """In a stealth repo, the findings for trmv's registry paths that show in the working tree."""
    if not (root / ".git").exists() or not any(f.stealth for f in present_files(root)):
        return []
    try:
        return stray_findings(root, stealth_registry())
    except ConfigError as exc:
        return [str(exc)]
