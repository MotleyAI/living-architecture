"""la-arch-migrate's 0.4.0 step against the shared exempt-move vectors."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from living_architecture.c4.exempt_move import ExemptNotMigratable, move_exempt

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir())
CASES: list[dict[str, Any]] = yaml.safe_load(
    (REPO_ROOT / "shared" / "vectors" / "exempt-move.yaml").read_text(encoding="utf-8")
)["cases"]


@pytest.mark.parametrize("case", [c for c in CASES if not c.get("refused")], ids=lambda c: c["name"])
def test_moved(case: dict[str, Any]) -> None:
    assert move_exempt(case["text"], "9.9.9") == case["moved"]


@pytest.mark.parametrize("case", [c for c in CASES if c.get("refused")], ids=lambda c: c["name"])
def test_refused(case: dict[str, Any]) -> None:
    with pytest.raises(ExemptNotMigratable):
        move_exempt(case["text"], "9.9.9")
