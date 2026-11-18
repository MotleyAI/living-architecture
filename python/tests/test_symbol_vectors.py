"""The shared symbol-path, compound-name and range-transform vectors, through the Python twin."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from living_architecture.lang.position_map import map_range
from living_architecture.refactor.compound import is_compound, words
from living_architecture.refactor.symbol_path import SymbolPath

VECTORS: dict[str, Any] = yaml.safe_load(
    (next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir()) / "shared/vectors/refactor-symbols.yaml")
    .read_text(encoding="utf-8")
)


@pytest.mark.parametrize("vector", VECTORS["paths"], ids=lambda v: v["name"])
def test_paths(vector: dict[str, Any]) -> None:
    parsed = SymbolPath.parse(vector["path"])
    if vector.get("invalid"):
        assert parsed is None
        return
    assert parsed is not None
    assert (list(parsed.segments), parsed.param, parsed.value) == (vector["segments"], vector.get("param"), vector.get("value"))


@pytest.mark.parametrize("vector", VECTORS["words"], ids=lambda v: v["name"])
def test_words(vector: dict[str, Any]) -> None:
    assert words(vector["name"]) == vector["words"]


@pytest.mark.parametrize("vector", VECTORS["compounds"], ids=lambda v: f"{v['old']}-{v['name']}")
def test_compounds(vector: dict[str, Any]) -> None:
    assert is_compound(vector["name"], vector["old"]) is vector["match"]


@pytest.mark.parametrize("vector", VECTORS["ranges"], ids=lambda v: v["name"])
def test_ranges(vector: dict[str, Any]) -> None:
    edits = [(s, e, n) for s, e, n in vector["edits"]]
    assert list(map_range(edits, *vector["range"])) == vector["mapped"]
