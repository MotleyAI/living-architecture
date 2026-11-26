"""The retired dr names never return: no tracked file names them, outside history and pending spec changes."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir())
RETIRED = re.compile(r"\bdr\b|\bdr[_./-]|\bDR_|\b[dD]r[A-Z]|deterministic[-_ ]refactor")
LOCKFILES = {"uv.lock", "package-lock.json"}
THIS_FILE = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()
CHANGES = "openspec/changes/"


def _tracked() -> list[str]:
    listed = subprocess.run(["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, check=True).stdout
    return [path for path in listed.decode("utf-8").split("\0") if path]


def _pending_specs() -> set[str]:
    """The corpus specs a non-archived change still rewrites: `openspec/specs/<cap>/spec.md` per delta."""
    changes = REPO_ROOT / CHANGES
    deltas = changes.glob("*/specs/*/") if changes.is_dir() else []
    return {f"openspec/specs/{d.name}/spec.md" for d in deltas if d.parent.parent.name != "archive"}


def _scanned(path: str, pending: set[str]) -> bool:
    return not (
        Path(path).name in LOCKFILES or path == THIS_FILE or path.startswith(CHANGES) or path in pending
    )


def test_no_tracked_text_names_a_retired_name() -> None:
    pending = _pending_specs()
    hits = []
    for path in filter(lambda p: _scanned(p, pending), _tracked()):
        file = REPO_ROOT / path
        if file.is_symlink() or not file.is_file():
            continue
        try:
            text = file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        hits += [f"{path}:{n}: {line.strip()}" for n, line in enumerate(text.splitlines(), 1) if RETIRED.search(line)]
    assert hits == []


def test_no_tracked_path_has_a_dr_component() -> None:
    assert [path for path in _tracked() if not path.startswith(CHANGES) and "dr" in path.split("/")] == []
