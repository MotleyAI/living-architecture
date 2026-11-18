"""Routing files to their language and collecting each language's conventions facts, natively or from its twin."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from living_architecture import __version__, lang, twin
from living_architecture.contract import contract_hash, language_of, message

__all__ = ["FactsError", "collect", "emit", "language_of"]


class FactsError(Exception):
    """The facts of another language could not be had; the message (if any) is printed, exit 2."""


def by_language(paths: list[str]) -> dict[str, list[str]]:
    """Known-extension paths grouped by language, each in input order."""
    out: dict[str, list[str]] = {}
    for path in paths:
        lang_id = language_of(path)
        if lang_id is not None:
            out.setdefault(lang_id, []).append(path)
    return out


def collect(paths: list[str], *, cwd: Path, repo_root: Path) -> dict[str, dict[str, Any]]:
    """Facts entry per path (all with a known extension, relative to `cwd`); FactsError when a twin fails."""
    out: dict[str, dict[str, Any]] = {}
    for lang_id, group in by_language(paths).items():
        if lang_id == twin.NATIVE_LANGUAGE:
            entries = lang.conventions_facts(cwd, group)
        else:
            try:
                entries = twin.request_conventions_facts(lang_id, cwd=cwd, paths=group, repo_root=repo_root)
            except twin.RelayedFailure as exc:
                raise FactsError("") from exc
            except twin.TwinError as exc:
                raise FactsError(str(exc)) from exc
        out.update((entry["path"], entry) for entry in entries)
    return out


def emit(lang_id: str, *, cwd: Path) -> int:
    """The facts server: the stdin JSON path list's facts document on stdout; only the native language."""
    if lang_id != twin.NATIVE_LANGUAGE:
        print(message("conventions.error", error=message("twin.not-native", language=lang_id)), file=sys.stderr)
        return 2
    try:
        paths = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        paths = None
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        print(message("conventions.error", error=message("conventions.facts-stdin-invalid")), file=sys.stderr)
        return 2
    document = {
        "language": lang_id,
        "version": __version__,
        "contract_hash": contract_hash(),
        "files": lang.conventions_facts(cwd, paths),
    }
    print(json.dumps(document))
    return 0
