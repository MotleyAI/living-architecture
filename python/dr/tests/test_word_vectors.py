"""The shared word-replacement vectors, through the Python twin."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from deterministic_refactor import refactor

VECTORS: dict[str, Any] = yaml.safe_load(
    (next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir()) / "shared/vectors/refactor-words.yaml")
    .read_text(encoding="utf-8")
)
NAMES = [(case["words"], vector) for case in VECTORS["cases"] for vector in case["names"]]
IDS = [f"{case['name']}: {vector['name']}" for case in VECTORS["cases"] for vector in case["names"]]


def test_the_vectors_cover_every_case_form() -> None:
    assert len(NAMES) > 40


@pytest.mark.parametrize(("table", "vector"), NAMES, ids=IDS)
def test_held_words(table: dict[str, str], vector: dict[str, Any]) -> None:
    assert refactor.held_words(vector["name"], table) == vector["held"]


@pytest.mark.parametrize(("table", "vector"), NAMES, ids=IDS)
def test_new_name(table: dict[str, str], vector: dict[str, Any]) -> None:
    assert refactor.replace_words(vector["name"], table) == vector["new_name"]
