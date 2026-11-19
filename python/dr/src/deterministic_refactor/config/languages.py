"""The repo's languages, and the public language facts `lang.<language>.<key>`."""

from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path
from typing import Any

from deterministic_refactor.config.load import ConfigError, LanguageSettings
from deterministic_refactor.contract import language, language_ids, language_keys, message


def source_files(root: Path, exempt: list[str]) -> list[str]:
    """Tracked and untracked-but-not-ignored files, minus the exempt globs; none outside git.

    ConfigError when git fails inside a repo.
    """
    in_repo = (root / ".git").exists()
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root, capture_output=True, check=False
        )
    except OSError as exc:
        if in_repo:
            raise ConfigError(message("config.git-failed")) from exc
        return []
    if proc.returncode != 0 and in_repo:
        raise ConfigError(message("config.git-failed"))
    paths = proc.stdout.decode("utf-8", "surrogateescape").split("\0")
    return [p for p in paths if p and not any(fnmatch.fnmatch(p, pat) for pat in exempt)]


def repo_languages(root: Path, settings: LanguageSettings) -> list[str]:
    """Languages with an explicit typecheck command, or with a root marker and a counted file; registry order."""
    explicit = settings.explicit
    files: list[str] | None = None
    out = []
    for lang_id in language_ids():
        if lang_id in explicit and getattr(settings.typecheck, lang_id) is not None:
            out.append(lang_id)
            continue
        entry = language(lang_id)
        if not any((root / marker).is_file() for marker in entry["markers"]):
            continue
        files = source_files(root, settings.exempt) if files is None else files
        if any(f.endswith(tuple(entry["source_extensions"])) for f in files):
            out.append(lang_id)
    return out


def language_fact(lang_id: str, key: str) -> Any:
    """A public fact of a registered language; KeyError for any other language or key."""
    if lang_id not in language_ids() or key not in language_keys():
        raise KeyError(key)
    entry = language(lang_id)
    if key == "source_globs":
        return [f"**/*{ext}" for ext in entry["source_extensions"]]
    if key == "waiver":
        return message("config.waiver", prefix=entry["comment_prefix"])
    return entry[key]
