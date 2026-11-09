"""Loading `architecture/index.yaml` and resolving where each language's code lives."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict

from living_architecture.c4 import INDEX_REL
from living_architecture.contract import YAMLError, language_ids, load_yaml, message, schema, validate


class ArchCheckError(Exception):
    """The architecture setup is too broken to check."""


class Layout(BaseModel):
    """Architecture, docs and specs live under `repo_root`; one language's code lives in disjoint roots under `source_root`."""

    model_config = ConfigDict(frozen=True)

    repo_root: Path
    source_root: Path
    root_packages: list[str]


def declared_languages(index: dict[str, Any]) -> list[str]:
    """The index's language sections, in language id order."""
    return sorted(key for key in index if key in language_ids())


def _first_duplicate(roots: list[str]) -> str | None:
    seen: set[str] = set()
    for root in roots:
        if root in seen:
            return root
        seen.add(root)
    return None


def _root_configuration(section: Any) -> tuple[str, list[str]]:
    """The section's root key and roots; ArchCheckError, never a schema error, unless one well-formed form is set."""
    has_package = isinstance(section, dict) and "root_package" in section
    has_packages = isinstance(section, dict) and "root_packages" in section
    if has_package and has_packages:
        raise ArchCheckError(message("arch-check.root-config-required"))
    if not has_packages:
        root = section.get("root_package") if has_package else None
        if not isinstance(root, str) or not root:
            raise ArchCheckError(message("arch-check.root-package-missing"))
        return "root_package", [root]
    roots = section["root_packages"]
    if not isinstance(roots, list) or not roots or not all(isinstance(root, str) and root for root in roots):
        raise ArchCheckError(message("arch-check.root-packages-invalid"))
    roots = cast(list[str], roots)
    duplicate = _first_duplicate(roots)
    if duplicate is not None:
        raise ArchCheckError(message("arch-check.root-packages-overlap", first=duplicate, second=duplicate))
    return "root_packages", roots


def load_index(root: Path) -> dict[str, Any]:
    try:
        index = load_yaml((root / INDEX_REL).read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise ArchCheckError(message("c4.index-invalid-yaml")) from exc
    except YAMLError as exc:
        raise ArchCheckError(f"{INDEX_REL}: {exc}") from exc
    except OSError as exc:
        raise ArchCheckError(str(exc)) from exc
    if not isinstance(index, dict):
        raise ArchCheckError(message("arch-check.index-not-mapping"))
    languages = declared_languages(index)
    if not languages:
        raise ArchCheckError(message("arch-check.no-language-section"))
    for language in languages:
        _ = _root_configuration(index[language])
    errors = validate(schema("index"), index)
    if errors:
        raise ArchCheckError(f"{INDEX_REL}: " + "; ".join(errors))
    return index


def _contained(
    base: Path, key: str, value: str, escapes_id: str, *, canonical_id: str | None = None, **values: object
) -> Path:
    """`base / value`, which must stay under `base` (symlinks included); with `canonical_id`, no empty or `.` segments."""
    rel = Path(value)
    if not value or rel.is_absolute():
        raise ArchCheckError(message("arch-check.layout-not-relative", key=key, value=value))
    if ".." in rel.parts:
        raise ArchCheckError(message("arch-check.layout-parent-segment", key=key, value=value))
    if canonical_id is not None and any(s in ("", ".") for s in value.split("/")):
        raise ArchCheckError(message(canonical_id, value=value))
    try:
        resolved = (base / rel).resolve()
    except (ValueError, RuntimeError):  # NUL, or a symlink loop before 3.13: not a directory, as the caller reports
        return base / rel
    if not resolved.is_relative_to(base.resolve()):
        raise ArchCheckError(message(escapes_id, value=value, **values))
    return base / rel


def _resolve_root(source_root: Path, key: str, root: str, shown: str) -> Path:
    """One root's real directory; ArchCheckError, naming `key`, unless it is a directory under `source_root`."""
    ids = f"arch-check.{key.replace('_', '-')}"
    package_dir = _contained(
        source_root, key, root, f"{ids}-escapes", canonical_id=f"{ids}-not-canonical", source_root=shown
    )
    if not package_dir.is_dir():
        raise ArchCheckError(message(f"{ids}-not-a-directory", value=root, source_root=shown))
    return package_dir.resolve()


def _roots_overlap(first: Path, second: Path) -> bool:
    return first == second or first in second.parents or second in first.parents


def _resolve_roots(source_root: Path, key: str, roots: list[str], shown: str) -> None:
    """ArchCheckError unless every root resolves under `source_root` and no two are equal or nested."""
    resolved: list[tuple[str, Path]] = []
    for root in roots:
        path = _resolve_root(source_root, key, root, shown)
        for previous, previous_path in resolved:
            if _roots_overlap(previous_path, path):
                raise ArchCheckError(message("arch-check.root-packages-overlap", first=previous, second=root))
        resolved.append((root, path))


def resolve_layout(repo_root: Path, section: dict[str, Any]) -> Layout:
    """Where one language's code lives; ArchCheckError unless its roots are disjoint directories under `source_root`."""
    key, roots = _root_configuration(section)
    value = section.get("source_root")
    source_root = repo_root
    if value is not None:
        source_root = _contained(repo_root, "source_root", value, "arch-check.source-root-escapes")
        if not source_root.is_dir():
            raise ArchCheckError(message("arch-check.source-root-not-a-directory", value=value))
    shown = "." if value is None else value
    _resolve_roots(source_root, key, roots, shown)
    return Layout(repo_root=repo_root, source_root=source_root, root_packages=roots)
