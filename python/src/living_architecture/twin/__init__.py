"""Reaching the other twin: identity handshake, discovery on PATH, runner probe and facts transport."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
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


def _discover_dir(lang: str, repo_root: Path) -> Path | None:
    """The first directory (each real path once) whose executable `la-doctor` qualifies."""
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


def _valid_facts(document: dict[str, Any], lang: str, expected_units: list[str]) -> bool:
    if validate(schema("facts"), document):
        return False
    if (document["language"], document["version"], document["contract_hash"]) != (lang, __version__, contract_hash()):
        return False
    return {u["unit"] for u in document["units"]} >= set(expected_units)


def request_facts(lang: str, repo_root: Path, expected_units: list[str]) -> dict[str, Any]:
    """`lang`'s facts from its twin, schema-checked; RelayedFailure when its run fails, TwinError otherwise."""
    refuse_if_forwarded(lang)
    argv = [*_launcher(lang, repo_root).argv("la-arch-check"), "--root", str(repo_root), "--language", lang, "--emit", "facts"]
    proc = subprocess.run(argv, stdout=subprocess.PIPE, env=_env(), check=False)
    if proc.returncode > 0:
        raise RelayedFailure
    try:
        document = json.loads(proc.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        document = None
    if proc.returncode < 0 or not isinstance(document, dict) or not _valid_facts(document, lang, expected_units):
        raise TwinError(_hint("twin.facts-invalid", lang))
    return document
