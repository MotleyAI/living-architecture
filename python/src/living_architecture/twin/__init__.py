"""Reaching the other twin: identity handshake, discovery on PATH, runner probe, facts transport and language runs."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from living_architecture import __version__
from living_architecture.contract import contract_hash, language, message, render_template, schema, validate

NATIVE_LANGUAGE = "python"
FORWARDED_ENV = "LA_FORWARDED"


class TwinError(Exception):
    """The other twin cannot serve the request; the message is the hint to print."""


class RelayedFailure(Exception):
    """The other twin's facts run failed; its stderr was already passed through."""


def identity() -> str:
    """This twin's `la-doctor --twin` line."""
    return f"{NATIVE_LANGUAGE} {__version__} {contract_hash()}"


def _expected(lang: str) -> str:
    return f"{lang} {__version__} {contract_hash()}"


def _hint(template_id: str, lang: str) -> str:
    install = render_template(language(lang)["install"], {"version": __version__})
    return message(template_id, language=lang, version=__version__, install=install)


def _env() -> dict[str, str]:
    return {**os.environ, FORWARDED_ENV: "1"}


class _Launcher:
    """Runs the other twin's commands: from one bin directory, or through its runner."""

    def __init__(self, directory: Path | None, runner: list[str]) -> None:
        self.directory = directory
        self.runner = runner

    def argv(self, command: str) -> list[str]:
        return [str(self.directory / command)] if self.directory is not None else [*self.runner, command]


def _qualifies(argv: list[str], lang: str) -> bool:
    """`argv` (an `la-doctor --twin` invocation) reports `lang` at this version and contract."""
    try:
        proc = subprocess.run(argv, capture_output=True, env=_env(), check=False)
    except OSError:
        return False
    return proc.returncode == 0 and proc.stdout.decode("utf-8", "replace").strip() == _expected(lang)


def _candidate_dirs(repo_root: Path) -> list[Path]:
    dirs = [Path(d) for d in os.environ.get("PATH", "").split(os.pathsep) if d]
    return [*dirs, repo_root / "node_modules" / ".bin"]


def _own_doctor() -> Path | None:
    """The real path of the running entry point's sibling `la-doctor`; None when it is not a file."""
    try:
        doctor = (Path(sys.argv[0]).resolve().parent / "la-doctor").resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    return doctor if doctor.is_file() else None


def _is_own(doctor: Path, own: Path | None) -> bool:
    try:
        return own is not None and doctor.resolve(strict=True) == own
    except (OSError, RuntimeError):
        return False


def _discover_dir(lang: str, repo_root: Path) -> Path | None:
    """The first directory (each real path once, never our own) whose executable `la-doctor` qualifies."""
    own = _own_doctor()
    probed: set[Path] = set()
    for directory in _candidate_dirs(repo_root):
        try:
            real = directory.resolve()
        except (OSError, RuntimeError):
            continue
        if real in probed:
            continue
        probed.add(real)
        doctor = directory / "la-doctor"
        if _is_own(doctor, own):
            continue
        if doctor.is_file() and os.access(doctor, os.X_OK) and _qualifies([str(doctor), "--twin"], lang):
            return directory
    return None


def _launcher(lang: str, repo_root: Path) -> _Launcher:
    """How to run the `lang` twin's commands; TwinError when no twin qualifies."""
    directory = _discover_dir(lang, repo_root)
    if directory is not None:
        return _Launcher(directory, [])
    runner = shlex.split(render_template(language(lang)["runner"], {"version": __version__}))
    if shutil.which(runner[0]) is not None and _qualifies([*runner, "la-doctor", "--twin"], lang):
        return _Launcher(None, runner)
    raise TwinError(_hint("twin.unavailable", lang))


def refuse_if_forwarded(lang: str) -> None:
    if os.environ.get(FORWARDED_ENV) == "1":
        raise TwinError(message("twin.forward-refused", language=lang))


def _identity_ok(document: dict[str, Any], lang: str) -> bool:
    return (document["language"], document["version"], document["contract_hash"]) == (lang, __version__, contract_hash())


def _document(proc: subprocess.CompletedProcess[bytes], schema_name: str, lang: str) -> dict[str, Any] | None:
    """The run's stdout as a schema-valid document of `lang` at this version; RelayedFailure on a non-zero exit."""
    if proc.returncode > 0:
        raise RelayedFailure
    try:
        document = json.loads(proc.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if proc.returncode < 0 or not isinstance(document, dict) or validate(schema(schema_name), document):
        return None
    return document if _identity_ok(document, lang) else None


def request_facts(lang: str, repo_root: Path, expected_units: list[str]) -> dict[str, Any]:
    """`lang`'s facts from its twin, schema-checked; RelayedFailure when its run fails, TwinError otherwise."""
    refuse_if_forwarded(lang)
    argv = [*_launcher(lang, repo_root).argv("la-arch-check"), "--root", str(repo_root), "--language", lang, "--emit", "facts"]
    document = _document(subprocess.run(argv, stdout=subprocess.PIPE, env=_env(), check=False), "facts", lang)
    if document is None or not {u["unit"] for u in document["units"]} >= set(expected_units):
        raise TwinError(_hint("twin.facts-invalid", lang))
    return document


def request_conventions_facts(lang: str, *, cwd: Path, paths: list[str], repo_root: Path) -> list[dict[str, Any]]:
    """`lang`'s conventions facts for `paths` (relative to `cwd`), one per path in order; errors as `request_facts`."""
    refuse_if_forwarded(lang)
    argv = [*_launcher(lang, repo_root).argv("la-check-conventions"), "--language", lang, "--emit", "facts"]
    sys.stdout.flush()
    sys.stderr.flush()
    proc = subprocess.run(
        argv, input=json.dumps(paths).encode("utf-8"), stdout=subprocess.PIPE, cwd=cwd, env=_env(), check=False
    )
    document = _document(proc, "conventions-facts", lang)
    if document is None or [f["path"] for f in document["files"]] != paths:
        raise TwinError(_hint("twin.facts-invalid", lang))
    return document["files"]


def run_language(command: str, lang: str, args: list[str], *, cwd: Path, repo_root: Path) -> int:
    """`command --language lang ARGS` in the `lang` twin, streams relayed; its exit code (a signal: 2)."""
    refuse_if_forwarded(lang)
    argv = [*_launcher(lang, repo_root).argv(command), "--language", lang, *args]
    sys.stdout.flush()
    sys.stderr.flush()
    code = subprocess.run(argv, cwd=cwd, env=_env(), check=False).returncode
    return code if code >= 0 else 2
