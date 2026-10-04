"""`la-typecheck`: each applicable language's checker against its committed, only-shrinking baseline."""

from __future__ import annotations

import fnmatch
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from living_architecture import lang, twin
from living_architecture.config import ConfigError, LaConfig, explicit_typecheck, find_repo_root, load_config
from living_architecture.contract import language, language_ids, message


class CommandError(Exception):
    """The checker cannot be run; the message is printed, exit 2."""


def split_command(text: str) -> list[str]:
    """POSIX shell words without expansion (shared/vectors/command-split.yaml); ValueError when malformed."""
    return shlex.split(text)


def combined_exit(codes: list[int]) -> int:
    return max(codes, default=0)


def _err(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


def _command(config: LaConfig, lang_id: str) -> str | None:
    return getattr(config.commands.typecheck, lang_id)


def _source_files(root: Path, exempt: list[str]) -> list[str]:
    """Tracked and untracked-but-not-ignored files, minus the exempt globs."""
    proc = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root, capture_output=True, check=False
    )
    paths = proc.stdout.decode("utf-8", "surrogateescape").split("\0")
    return [p for p in paths if p and not any(fnmatch.fnmatch(p, pat) for pat in exempt)]


def applicable(root: Path, config: LaConfig) -> list[str]:
    """Languages set to a command explicitly, or with files and a root marker; `null` turns one off."""
    explicit = explicit_typecheck(root)
    files: list[str] | None = None
    out = []
    for lang_id in language_ids():
        if _command(config, lang_id) is None:
            continue
        if lang_id in explicit:
            out.append(lang_id)
            continue
        entry = language(lang_id)
        if not any((root / marker).is_file() for marker in entry["markers"]):
            continue
        files = _source_files(root, config.conventions.exempt) if files is None else files
        if any(f.endswith(tuple(entry["source_extensions"])) for f in files):
            out.append(lang_id)
    return out


def _executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def resolve_argv(root: Path, lang_id: str, command: str) -> list[str]:
    """The command's words with its first one resolved: a path from the repo root, else local bin dir, then PATH."""
    try:
        words = split_command(command)
    except ValueError:
        words = []
    if not words:
        raise CommandError(message("typecheck.bad-command", language=lang_id, command=command))
    local_bin = language(lang_id)["local_bin"]
    if "/" in words[0]:
        found = str(root / words[0]) if _executable(root / words[0]) else None
    else:
        found = str(root / local_bin / words[0]) if _executable(root / local_bin / words[0]) else shutil.which(words[0])
    if found is None:
        raise CommandError(message("typecheck.not-found", language=lang_id, command=words[0], local_bin=local_bin))
    return [found, *words[1:]]


def _run_python(root: Path, argv: list[str], *, write: bool) -> int:
    baseline = root / language("python")["baseline_file"]
    flag = [lang.BASEDPYRIGHT_WRITE_FLAG] if write else []
    code = lang.basedpyright_exit(subprocess.run([*argv, *flag], cwd=root, check=False).returncode, write=write)
    if write and code == 0:
        if not baseline.exists():
            baseline.parent.mkdir(parents=True, exist_ok=True)
            baseline.write_text(lang.empty_basedpyright_baseline(), encoding="utf-8")
        _err(message("typecheck.write", language="python", baseline=language("python")["baseline_file"]))
    return code


def _check_native(root: Path, command: str, *, write: bool) -> int:
    try:
        argv = resolve_argv(root, twin.NATIVE_LANGUAGE, command)
    except CommandError as exc:
        _err(str(exc))
        return 2
    sys.stdout.flush()
    return _run_python(root, argv, write=write)


def _check(root: Path, lang_id: str, command: str, *, write: bool) -> int:
    if lang_id == twin.NATIVE_LANGUAGE:
        return _check_native(root, command, write=write)
    try:
        return twin.run_language("la-typecheck", lang_id, ["--write-baseline"] if write else [], cwd=root, repo_root=root)
    except twin.TwinError as exc:
        _err(message("typecheck.error", error=str(exc)))
        return 2


def _setup(cwd: Path) -> tuple[Path, LaConfig] | int:
    root = find_repo_root(cwd)
    if not (root / ".git").exists():
        _err(message("typecheck.not-git"))
        return 2
    try:
        return root, load_config(root)
    except ConfigError as exc:
        _err(message("typecheck.error", error=str(exc)))
        return 2


def run(*, cwd: Path, write: bool, language_id: str | None) -> int:
    """`la-typecheck`; with `language_id` (the twins' protocol) only that native language, without a header."""
    setup = _setup(cwd)
    if isinstance(setup, int):
        return setup
    root, config = setup
    if language_id is not None:
        if language_id != twin.NATIVE_LANGUAGE:
            _err(message("typecheck.error", error=message("typecheck.not-native", language=language_id)))
            return 2
        return _check_native(root, _command(config, language_id) or "", write=write)
    languages = applicable(root, config)
    if not languages:
        _err(message("typecheck.no-languages"))
        return 0
    codes = []
    for lang_id in languages:
        command = _command(config, lang_id) or ""
        _err(message("typecheck.header", language=lang_id, command=command))
        baseline = language(lang_id)["baseline_file"]
        if write and (root / baseline).exists():
            _err(message("typecheck.skip", language=lang_id, baseline=baseline))
            continue
        codes.append(_check(root, lang_id, command, write=write))
    if write and not codes:
        _err(message("typecheck.refusal"))
        return 2
    return combined_exit(codes)
