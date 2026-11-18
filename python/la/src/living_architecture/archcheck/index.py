"""Loading `architecture/index.yaml` and resolving where each language's code lives."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict

from deterministic_refactor.contract import (
    DuplicateKeyError,
    YAMLError,
    language_ids,
    load_yaml,
    message,
    os_error_text,
    schema,
    validate,
)
from living_architecture.c4 import INDEX_REL


class ArchCheckError(Exception):
    """The architecture setup is too broken to check."""


class SourceRoot(BaseModel):
    """An import root and the configured root packages under it."""

    model_config = ConfigDict(frozen=True)

    path: Path
    root_packages: list[str]


class Layout(BaseModel):
    """Architecture, docs and specs live under `repo_root`; one language's code lives in disjoint roots under its source roots."""

    model_config = ConfigDict(frozen=True)

    repo_root: Path
    source_roots: list[SourceRoot]


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


def _source_roots_configuration(section: Any) -> None:
    """ArchCheckError, never a schema error, when `source_roots` is set with `source_root` or is malformed."""
    if not isinstance(section, dict) or "source_roots" not in section:
        return
    if "source_root" in section:
        raise ArchCheckError(message("arch-check.source-roots-both"))
    entries = section["source_roots"]
    if not isinstance(entries, list) or not entries or not all(isinstance(e, str) and e for e in entries):
        raise ArchCheckError(message("arch-check.source-roots-invalid"))
    duplicate = _first_duplicate(cast(list[str], entries))
    if duplicate is not None:
        raise ArchCheckError(message("arch-check.source-roots-overlap", first=duplicate, second=duplicate))


def load_index(root: Path) -> dict[str, Any]:
    """The validated index mapping; ArchCheckError when it is unusable."""
    path = root / INDEX_REL
    try:
        index = load_yaml(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise ArchCheckError(message("yaml.invalid", path=INDEX_REL)) from exc
    except DuplicateKeyError as exc:
        raise ArchCheckError(f"{INDEX_REL}: {exc}") from exc
    except YAMLError as exc:
        raise ArchCheckError(message("yaml.invalid", path=INDEX_REL)) from exc
    except OSError as exc:
        raise ArchCheckError(os_error_text(exc, root, path)) from exc
    if not isinstance(index, dict):
        raise ArchCheckError(message("arch-check.index-not-mapping"))
    languages = declared_languages(index)
    if not languages:
        raise ArchCheckError(message("arch-check.no-language-section"))
    for language in languages:
        _ = _root_configuration(index[language])
    if "python" in languages:
        _source_roots_configuration(index["python"])
    errors = validate(schema("index"), index)
    if errors:
        raise ArchCheckError(f"{INDEX_REL}: " + "; ".join(errors))
    return index


def _relative(key: str, value: str, canonical_id: str | None) -> Path:
    """`value` as a relative path; ArchCheckError if absolute, with a `..` segment, or (with `canonical_id`) non-canonical."""
    rel = Path(value)
    if not value or rel.is_absolute():
        raise ArchCheckError(message("arch-check.layout-not-relative", key=key, value=value))
    if ".." in rel.parts:
        raise ArchCheckError(message("arch-check.layout-parent-segment", key=key, value=value))
    if canonical_id is not None and any(s in ("", ".") for s in value.split("/")):
        raise ArchCheckError(message(canonical_id, value=value))
    return rel


def _contained(
    base: Path, key: str, value: str, escapes_id: str, *, canonical_id: str | None = None, **values: object
) -> Path:
    """`base / value`, which must stay under `base` (symlinks included); with `canonical_id`, no empty or `.` segments."""
    rel = _relative(key, value, canonical_id)
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


def _add_disjoint(resolved: list[tuple[str, Path]], name: str, path: Path, overlap_id: str) -> None:
    """Append `(name, path)`; ArchCheckError when `path` equals or nests with an earlier one."""
    for previous, previous_path in resolved:
        if _roots_overlap(previous_path, path):
            raise ArchCheckError(message(overlap_id, first=previous, second=name))
    resolved.append((name, path))


def _resolve_source_roots(repo_root: Path, entries: list[str]) -> list[tuple[str, Path]]:
    """Each `source_roots` entry with its directory; ArchCheckError unless they are disjoint directories in the repo."""
    resolved: list[tuple[str, Path]] = []
    real: list[tuple[str, Path]] = []
    for entry in entries:
        path = _contained(
            repo_root, "source_roots", entry, "arch-check.source-roots-escapes",
            canonical_id="arch-check.source-roots-not-canonical",
        )
        if not path.is_dir():
            raise ArchCheckError(message("arch-check.source-roots-not-a-directory", value=entry))
        _add_disjoint(real, entry, path.resolve(), "arch-check.source-roots-overlap")
        resolved.append((entry, path))
    return resolved


def _holder(key: str, root: str, source_roots: list[tuple[str, Path]]) -> tuple[str, Path]:
    """The one source root holding `root`; ArchCheckError when none or several do."""
    rel = _relative(key, root, f"arch-check.{key.replace('_', '-')}-not-canonical")
    holders = [(entry, path) for entry, path in source_roots if (path / rel).is_dir()]
    if not holders:
        raise ArchCheckError(message("arch-check.source-roots-none", value=root))
    if len(holders) > 1:
        raise ArchCheckError(message("arch-check.source-roots-several", value=root, roots=[e for e, _ in holders]))
    return holders[0]


def _layout_under_source_roots(repo_root: Path, key: str, roots: list[str], entries: list[str]) -> Layout:
    """The layout of a section with `source_roots`: each root under exactly one entry, every entry used."""
    source_roots = _resolve_source_roots(repo_root, entries)
    held: dict[str, list[str]] = {entry: [] for entry in entries}
    resolved: list[tuple[str, Path]] = []
    for root in roots:
        entry, path = _holder(key, root, source_roots)
        _add_disjoint(resolved, root, _resolve_root(path, key, root, entry), "arch-check.root-packages-overlap")
        held[entry].append(root)
    for entry in entries:
        if not held[entry]:
            raise ArchCheckError(message("arch-check.source-roots-unused", value=entry))
    return Layout(
        repo_root=repo_root,
        source_roots=[SourceRoot(path=path, root_packages=held[entry]) for entry, path in source_roots],
    )


def resolve_layout(repo_root: Path, section: dict[str, Any]) -> Layout:
    """Where one language's code lives; ArchCheckError unless its roots are disjoint directories under its source roots."""
    key, roots = _root_configuration(section)
    entries = section.get("source_roots")
    if entries is not None:
        _source_roots_configuration(section)
        return _layout_under_source_roots(repo_root, key, roots, cast(list[str], entries))
    value = section.get("source_root")
    source_root = repo_root
    if value is not None:
        source_root = _contained(repo_root, "source_root", value, "arch-check.source-root-escapes")
        if not source_root.is_dir():
            raise ArchCheckError(message("arch-check.source-root-not-a-directory", value=value))
    shown = "." if value is None else value
    resolved: list[tuple[str, Path]] = []
    for root in roots:
        _add_disjoint(resolved, root, _resolve_root(source_root, key, root, shown), "arch-check.root-packages-overlap")
    return Layout(repo_root=repo_root, source_roots=[SourceRoot(path=source_root, root_packages=roots)])
