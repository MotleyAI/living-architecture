"""`la-affected-tests`: the test files a change can affect, its own language natively, the other through its twin."""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from living_architecture import NATIVE_LANGUAGE, __version__, changes, lang, twin
from living_architecture.config import ConfigError, find_repo_root
from living_architecture.contract import (
    contract_hash,
    is_test_file,
    language,
    language_ids,
    language_of,
    message,
    schema,
    validate,
)

__all__ = ["run", "serve"]


class Change(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    deleted: bool


class AffectedError(Exception):
    """The command cannot complete; the message (if any) is printed, exit 2."""


def _check_path(path: str) -> str:
    """`path` when it can be printed one per line; AffectedError naming it otherwise."""
    try:
        path.encode("utf-8")
    except UnicodeEncodeError:
        pass
    else:
        if "\n" not in path and "\r" not in path:
            return path
    shown = path.encode("utf-8", "surrogateescape").decode("utf-8", "replace")
    raise AffectedError(message("affected.unrepresentable-path", path=shown))


def _byte_order(paths: list[str]) -> list[str]:
    return sorted(set(paths), key=lambda p: p.encode("utf-8", "surrogateescape"))


def _has_extension(path: str, lang_id: str) -> bool:
    return any(path.endswith(ext) for ext in language(lang_id)["source_extensions"])


def _repo_files(repo_root: Path) -> list[str]:
    """Tracked and untracked-not-ignored paths, in byte order."""
    return _byte_order(changes.git_paths(["ls-files", "-z", "--cached", "--others", "--exclude-standard"], repo_root=repo_root))


def _computed(changed: list[Change], repo_root: Path, repo_files: list[str]) -> list[str]:
    """Languages with a changed file, or importing non-source files when one changed and the repo has their files."""
    non_source = any(language_of(c.path) is None for c in changed)
    out = []
    for lang_id in language_ids():
        touched = any(language_of(c.path) == lang_id for c in changed)
        reaches = (
            non_source
            and language(lang_id)["imports_non_source"]
            and any(_has_extension(p, lang_id) and os.path.lexists(repo_root / p) for p in repo_files)
        )
        if touched or reaches:
            out.append(lang_id)
    return out


def select(lang_id: str, changed: list[Change], repo_root: Path, repo_files: list[str]) -> list[str]:
    """`lang_id`'s changed tests and the tests whose imports reach a changed file."""
    non_source = language(lang_id)["imports_non_source"]
    owned = [c for c in changed if language_of(c.path) == lang_id or (non_source and language_of(c.path) is None)]
    deleted = sorted(c.path for c in owned if c.deleted)
    candidates = [_check_path(p) for p in repo_files if _has_extension(p, lang_id)]
    files = sorted(p for p in candidates if os.path.lexists(repo_root / p))
    importers: dict[str, set[str]] = defaultdict(set)
    for src, dst in lang.dependency_edges(repo_root, files=files, deleted=deleted):
        importers[dst].add(src)
    starts = [c.path for c in owned]
    reached = set(starts)
    queue = list(starts)
    while queue:
        for importer in importers[queue.pop()]:
            if importer not in reached:
                reached.add(importer)
                queue.append(importer)
    gone = {c.path for c in changed if c.deleted}
    return sorted(p for p in reached - gone if language_of(p) == lang_id and is_test_file(p))


def _changes(repo_root: Path, base: str) -> list[Change]:
    base_ref = changes.resolve_base_ref(base=base, repo_root=repo_root)
    listed = changes.changed_paths(base_ref=base_ref, repo_root=repo_root, deletions=True, untracked=True)
    checked = {p: _check_path(p) for p in _byte_order(listed)}
    return [Change(path=checked[p], deleted=not os.path.lexists(repo_root / p)) for p in listed]


def _request(lang_id: str, changed: list[Change], repo_root: Path) -> list[str]:
    try:
        return twin.request_affected(lang_id, [c.model_dump() for c in changed], repo_root=repo_root)
    except twin.RelayedFailure as exc:
        raise AffectedError("") from exc
    except twin.TwinError as exc:
        raise AffectedError(str(exc)) from exc


def _fail(error: str) -> int:
    if error:
        print(message("affected.error", error=error), file=sys.stderr)
    return 2


def run(*, base: str, cwd: Path) -> int:
    """The public command: every computed language's selection, unioned, one path per line."""
    repo_root = find_repo_root(cwd)
    try:
        changed = _changes(repo_root, base)
        repo_files = _repo_files(repo_root)
        selected: set[str] = set()
        for lang_id in _computed(changed, repo_root, repo_files):
            if lang_id == NATIVE_LANGUAGE:
                selected.update(select(lang_id, changed, repo_root, repo_files))
            else:
                selected.update(_request(lang_id, changed, repo_root))
    except (ConfigError, AffectedError) as exc:
        return _fail(str(exc))
    for path in sorted(selected):
        print(path)
    return 0


def serve(lang_id: str, *, cwd: Path) -> int:
    """The internal request: the stdin change list's native selection as a JSON document."""
    if lang_id != NATIVE_LANGUAGE:
        return _fail(message("twin.not-native", language=lang_id))
    try:
        document = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        document = None
    if document is None or validate(schema("affected-request"), document):
        return _fail(message("affected.request-invalid"))
    changed = [Change(**c) for c in document["changes"]]
    repo_root = find_repo_root(cwd)
    try:
        tests = select(lang_id, changed, repo_root, _repo_files(repo_root))
    except (ConfigError, AffectedError) as exc:
        return _fail(str(exc))
    print(json.dumps({"language": lang_id, "version": __version__, "contract_hash": contract_hash(), "tests": tests}))
    return 0
