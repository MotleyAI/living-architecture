"""basedpyright as la-typecheck's Python checker: its baseline flag, exit codes and the pyright#11919 patch."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

BASEDPYRIGHT_WRITE_FLAG = "--writebaseline"
# Remove with the preload once basedpyright ships the fix for microsoft/pyright#11919.
PYRIGHT_PATCH_PRELOAD = Path(__file__).with_name("pyright_patch.cjs")


class PyrightPatch(BaseModel):
    """What the preload recorded for the basedpyright bundle it saw."""

    outcome: Literal["patched", "unverified", "mismatch"]
    version: str
    count: int


def basedpyright_exit(code: int, *, write: bool) -> int:
    """0 and 1 pass through (write mode: both mean written, so 0); anything else, a signal included, is 2."""
    if code in (0, 1):
        return 0 if write else code
    return 2


def empty_basedpyright_baseline() -> str:
    """The baseline of a clean project, which basedpyright itself does not write."""
    return '{\n  "files": {}\n}\n'


def pyright_patch_env(
    base: Mapping[str, str], *, result: Path, versions: list[str], preload: Path = PYRIGHT_PATCH_PRELOAD
) -> dict[str, str]:
    """A copy of `base` that loads the preload after any inherited NODE_OPTIONS and tells it where to record."""
    quoted = str(preload).replace("\\", "\\\\").replace('"', '\\"')
    require = f'--require "{quoted}"'
    inherited = base.get("NODE_OPTIONS", "")
    return {
        **base,
        "NODE_OPTIONS": f"{inherited} {require}" if inherited else require,
        "LA_PYRIGHT_PATCH_RESULT": str(result),
        "LA_PYRIGHT_PATCH_VERSIONS": json.dumps(versions),
    }


def read_pyright_patch(path: Path) -> PyrightPatch | None:
    """The preload's record, or None when it recorded nothing."""
    if not path.exists():
        return None
    return PyrightPatch.model_validate_json(path.read_text(encoding="utf-8"))
