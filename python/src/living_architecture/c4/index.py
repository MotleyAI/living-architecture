"""Reads of `architecture/index.yaml` for diagram settings and migration; problems become messages."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from living_architecture.contract import DuplicateKeyError, YAMLError, load_yaml, message

INDEX_REL = "architecture/index.yaml"


class Index(BaseModel):
    """`architecture/index.yaml` as its exact text and as the mapping it holds."""

    text: str
    data: dict[Any, Any]


def load_index(root: Path) -> Index | str | None:
    """The index, a message explaining why it is unusable, or None when it is absent (never raises)."""
    path = root / INDEX_REL
    if not path.is_file():
        return None
    try:
        text = path.read_bytes().decode("utf-8")
        data = load_yaml(text)
    except DuplicateKeyError as exc:
        return message("c4.index-duplicate-key", error=str(exc))
    except (YAMLError, UnicodeDecodeError):
        return message("c4.index-invalid-yaml")
    return Index(text=text, data=data) if isinstance(data, dict) else message("c4.index-not-mapping")


def read_index(root: Path) -> dict[Any, Any] | str:
    """The parsed index mapping, or a message explaining why it is unusable (never raises)."""
    index = load_index(root)
    if index is None:
        return message("c4.index-missing")
    return index if isinstance(index, str) else index.data
