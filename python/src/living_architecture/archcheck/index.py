"""Loading `architecture/index.yaml` and resolving where the code lives."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from living_architecture.contract import YAMLError, load_yaml, message, schema, validate

INDEX_REL = "architecture/index.yaml"


class ArchCheckError(Exception):
    """The architecture setup is too broken to check."""


class Layout(BaseModel):
    """Architecture, docs and specs live under `repo_root`; code lives under `source_root`."""

    model_config = ConfigDict(frozen=True)

    repo_root: Path
    source_root: Path
    root_package: str


def load_index(root: Path) -> dict[str, Any]:
    try:
        index = load_yaml((root / INDEX_REL).read_text(encoding="utf-8"))
    except (OSError, YAMLError) as exc:
        raise ArchCheckError(str(exc)) from exc
    if not isinstance(index, dict):
        raise ArchCheckError(f"{INDEX_REL}: top level must be a mapping")
    pkg = index.get("root_package")
    if not isinstance(pkg, str) or not pkg:
        raise ArchCheckError(message("arch-check.root-package-missing"))
    errors = validate(schema("index"), index)
    if errors:
        raise ArchCheckError(f"{INDEX_REL}: " + "; ".join(errors))
    return index


def _source_root_problem(repo_root: Path, value: str, root_package: str) -> str | None:
    rel = Path(value)
    if not value or rel.is_absolute():
        return "must be a relative path"
    if ".." in rel.parts:
        return "must not contain '..'"
    resolved = (repo_root / rel).resolve()
    if not resolved.is_relative_to(repo_root.resolve()):
        return "resolves outside the repo"
    if not resolved.is_dir():
        return "is not a directory"
    if not (resolved / root_package).is_dir():
        return f"does not contain root_package {root_package!r}"
    return None


def resolve_layout(repo_root: Path, index: dict[str, Any]) -> Layout:
    root_package = index["root_package"]
    value = index.get("source_root")
    if value is None:
        return Layout(repo_root=repo_root, source_root=repo_root, root_package=root_package)
    problem = _source_root_problem(repo_root, value, root_package)
    if problem is not None:
        raise ArchCheckError(f"{INDEX_REL}: source_root {value!r} {problem}")
    return Layout(repo_root=repo_root, source_root=repo_root / value, root_package=root_package)
