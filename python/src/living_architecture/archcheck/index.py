"""Loading `architecture/index.yaml` and resolving where each language's code lives."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from living_architecture.contract import YAMLError, language_ids, load_yaml, message, schema, validate

INDEX_REL = "architecture/index.yaml"


class ArchCheckError(Exception):
    """The architecture setup is too broken to check."""


class Layout(BaseModel):
    """Architecture, docs and specs live under `repo_root`; one language's code lives under `source_root`."""

    model_config = ConfigDict(frozen=True)

    repo_root: Path
    source_root: Path
    root_package: str
    root_packages: list[str] = Field(default_factory=list)

    @property
    def configured_roots(self) -> list[str]:
        """The resolved roots, falling back to the original public single-root constructor shape."""
        return self.root_packages or [self.root_package]


def declared_languages(index: dict[str, Any]) -> list[str]:
    """The index's language sections, in language id order."""
    return sorted(key for key in index if key in language_ids())


def _validate_root_configuration(section: Any) -> None:
    """Require one supported root form and validate `root_packages` before schema validation."""
    has_package = isinstance(section, dict) and "root_package" in section
    has_packages = isinstance(section, dict) and "root_packages" in section
    if not has_package and not has_packages:
        raise ArchCheckError(message("arch-check.root-package-missing"))
    if has_package and has_packages:
        raise ArchCheckError(message("arch-check.root-config-required"))
    if not has_packages:
        return
    roots = section["root_packages"]
    if not isinstance(roots, list) or not roots or any(not isinstance(root, str) for root in roots):
        raise ArchCheckError(message("arch-check.root-packages-invalid"))


def load_index(root: Path) -> dict[str, Any]:
    try:
        index = load_yaml((root / INDEX_REL).read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise ArchCheckError(message("c4.index-invalid-yaml")) from exc
    except (OSError, YAMLError) as exc:
        raise ArchCheckError(str(exc)) from exc
    if not isinstance(index, dict):
        raise ArchCheckError(message("arch-check.index-not-mapping"))
    languages = declared_languages(index)
    if not languages:
        raise ArchCheckError(message("arch-check.no-language-section"))
    for language in languages:
        _validate_root_configuration(index[language])
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


def _root_configuration(section: dict[str, Any]) -> tuple[list[str], bool]:
    """Return validated root names and whether they use the multi-root form."""
    multiple = "root_packages" in section
    if not multiple:
        return [section.get("root_package", "")], False
    raw_roots = section.get("root_packages")
    if not isinstance(raw_roots, list) or not raw_roots or any(not isinstance(root, str) for root in raw_roots):
        raise ArchCheckError(message("arch-check.root-packages-invalid"))
    return cast(list[str], raw_roots), True


def _resolve_root_package(source_root: Path, root_package: str, shown: str, multiple: bool) -> Path:
    """Validate one configured root and return its resolved directory."""
    key = "root_packages" if multiple else "root_package"
    if multiple and any(part in ("", ".") for part in root_package.split("/")):
        raise ArchCheckError(message("arch-check.root-packages-not-canonical", value=root_package))
    escape_id = "arch-check.root-packages-escapes" if multiple else "arch-check.root-package-escapes"
    package_dir = _contained(source_root, key, root_package, escape_id, canonical=True, source_root=shown)
    if not package_dir.is_dir():
        error_id = "arch-check.root-packages-not-a-directory" if multiple else "arch-check.root-package-not-a-directory"
        raise ArchCheckError(message(error_id, value=root_package, source_root=shown))
    return package_dir.resolve()


def _roots_overlap(first: Path, second: Path) -> bool:
    """Return whether two resolved roots are equal or nested."""
    return first == second or first in second.parents or second in first.parents


def _resolve_roots(source_root: Path, roots: list[str], shown: str, multiple: bool) -> None:
    """Validate every root and reject equal or nested resolved directories."""
    resolved_roots: list[tuple[str, Path]] = []
    for root_package in roots:
        resolved = _resolve_root_package(source_root, root_package, shown, multiple)
        for previous, previous_path in resolved_roots:
            if _roots_overlap(previous_path, resolved):
                raise ArchCheckError(message("arch-check.root-packages-overlap", first=previous, second=root_package))
        resolved_roots.append((root_package, resolved))


def resolve_layout(repo_root: Path, section: dict[str, Any]) -> Layout:
    """Where one language's code lives; all configured roots must be disjoint directories under source_root."""
    roots, multiple = _root_configuration(section)
    value = section.get("source_root")
    source_root = repo_root
    if value is not None:
        source_root = _contained(repo_root, "source_root", value, "arch-check.source-root-escapes")
        if not source_root.is_dir():
            raise ArchCheckError(message("arch-check.source-root-not-a-directory", value=value))
    shown = "." if value is None else value
    _resolve_roots(source_root, roots, shown, multiple)
    return Layout(repo_root=repo_root, source_root=source_root, root_package=roots[0], root_packages=roots)
