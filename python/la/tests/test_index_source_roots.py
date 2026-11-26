"""The index schema's Python `source_roots`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from living_architecture.contract import validate

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir())
INDEX_SCHEMA = json.loads((REPO_ROOT / "shared" / "la" / "schema" / "index.schema.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("document", "valid"),
    [
        ({"python": {"source_roots": ["python/trmv/src", "python/la/src"],
                     "root_packages": ["trmv", "living_architecture"]}}, True),
        ({"python": {"source_roots": ["src"], "root_package": "pkg"}}, True),
        ({"python": {"source_root": "src", "source_roots": ["src"], "root_package": "pkg"}}, False),
        ({"typescript": {"source_roots": ["a", "b"], "root_package": "src"}}, False),
        ({"source_roots": ["src"], "python": {"root_package": "pkg"}}, False),
    ],
    ids=["workspace", "one-entry", "both-forms", "typescript", "top-level"],
)
def test_index_schema_source_roots(document: dict[str, Any], valid: bool) -> None:
    assert (validate(INDEX_SCHEMA, document) == []) is valid
