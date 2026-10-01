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
        raise ArchCheckError(message("arch-check.index-not-mapping"))
    pkg = index.get("root_package")
    if not isinstance(pkg, str) or not pkg:
        raise ArchCheckError(message("arch-check.root-package-missing"))
    errors = validate(schema("index"), index)
    if errors:
        raise ArchCheckError(f"{INDEX_REL}: " + "; ".join(errors))
    return index


def _contained(base: Path, key: str, value: str, escapes_id: str, *, canonical: bool = False, **values: object) -> Path:
    """`base / value`, which must stay under `base` (symlinks included); `canonical`: no empty or `.` segments."""
    rel = Path(value)
    if not value or rel.is_absolute():
        raise ArchCheckError(message("arch-check.layout-not-relative", key=key, value=value))
    if ".." in rel.parts:
        raise ArchCheckError(message("arch-check.layout-parent-segment", key=key, value=value))
    if canonical and any(s in ("", ".") for s in value.split("/")):
        raise ArchCheckError(message("arch-check.root-package-not-canonical", value=value))
    try:
        resolved = (base / rel).resolve()
    except (ValueError, RuntimeError):  # NUL, or a symlink loop before 3.13: not a directory, as the caller reports
        return base / rel
    if not resolved.is_relative_to(base.resolve()):
        raise ArchCheckError(message(escapes_id, value=value, **values))
    return base / rel


def resolve_layout(repo_root: Path, index: dict[str, Any]) -> Layout:
    """Where the code lives; ArchCheckError unless `source_root` and `root_package` are directories inside the repo."""
    root_package = index["root_package"]
    value = index.get("source_root")
    source_root = repo_root
    if value is not None:
        source_root = _contained(repo_root, "source_root", value, "arch-check.source-root-escapes")
        if not source_root.is_dir():
            raise ArchCheckError(message("arch-check.source-root-not-a-directory", value=value))
    shown = "." if value is None else value
    package_dir = _contained(source_root, "root_package", root_package, "arch-check.root-package-escapes", canonical=True, source_root=shown)
    if not package_dir.is_dir():
        raise ArchCheckError(message("arch-check.root-package-not-a-directory", value=root_package, source_root=shown))
    return Layout(repo_root=repo_root, source_root=source_root, root_package=root_package)
