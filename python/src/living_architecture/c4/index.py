"""Lenient reads of `architecture/index.yaml` for diagram settings; problems become findings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from living_architecture.contract import YAMLError, load_yaml, message


def read_index(root: Path) -> dict[Any, Any] | str:
    """The parsed index mapping, or a message explaining why it is unusable (never raises)."""
    index_path = root / "architecture" / "index.yaml"
    if not index_path.is_file():
        return message("c4.index-missing")
    try:
        index = load_yaml(index_path.read_text(encoding="utf-8"))
    except YAMLError:
        return message("c4.index-invalid-yaml")
    return index if isinstance(index, dict) else message("c4.index-not-mapping")
