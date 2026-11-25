"""Reaching the other twin: identity handshake, discovery on PATH, runner probe, facts transport and language runs."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from deterministic_refactor import NATIVE_LANGUAGE, __version__
from deterministic_refactor.contract import (
    DR,
    Snapshot,
    contract_hash,
    language,
    message,
    render_template,
    validate,
)

FORWARDED_ENV = "LA_FORWARDED"
_FACTS_INVALID = "twin.facts-invalid"


class TwinError(Exception):
    """The other twin cannot serve the request; the message is the hint to print."""


class RelayedFailure(Exception):
    """The other twin's facts run failed; its stderr was already passed through."""


class Identity(BaseModel):
    """A package's twin as the other twin's probe sees it: the package, the doctor answering `--twin`, its version,
    its contract hashes (its own first), and the contract holding the schemas of the documents it exchanges."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    package: str
    doctor: str
    version: str
    hashes: tuple[str, ...]
    contract: Snapshot

    def line(self, lang: str) -> str:
        """The `--twin` line the package's twin of `lang` prints."""
        return " ".join((lang, self.version, *self.hashes))


def dr_identity() -> Identity:
    """dr's twin identity."""
    cli = DR.yaml("cli.yaml")
    return Identity(package=cli["package"], doctor=cli["doctor"], version=__version__, hashes=(contract_hash(),), contract=DR)


def identity(who: Identity | None = None) -> str:
    """This twin's `--twin` line for `who` (default: dr)."""
    return (who or dr_identity()).line(NATIVE_LANGUAGE)


def install_command(lang: str, who: Identity, version: str | None = None) -> str:
    """The command installing `who`'s twin of `lang` at `version` (default: its own)."""
    return render_template(language(lang)["install"][who.package], {"version": version or who.version})


def _hint(template_id: str, lang: str, who: Identity) -> str:
    """The hint `template_id` from `who`'s registry, else from dr's."""
    values = {"language": lang, "package": who.package, "version": who.version, "install": install_command(lang, who)}
    template = who.contract.findings().get(template_id)
    return message(template_id, **values) if template is None else render_template(template, values)


def _env() -> dict[str, str]:
    return {**os.environ, FORWARDED_ENV: "1"}


class _Launcher:
    """Runs the other twin's commands: from one bin directory, or through its runner."""

    def __init__(self, directory: Path | None, runner: list[str]) -> None:
        self.directory = directory
        self.runner = runner

    def argv(self, command: str) -> list[str]:
        return [str(self.directory / command)] if self.directory is not None else [*self.runner, command]


def _qualifies(argv: list[str], lang: str, who: Identity) -> bool:
    """`argv` (a doctor's `--twin` invocation) reports `who`'s twin of `lang`."""
    try:
        proc = subprocess.run(argv, capture_output=True, env=_env(), check=False)
    except OSError:
        return False
    return proc.returncode == 0 and proc.stdout.decode("utf-8", "replace").strip() == who.line(lang)


def _candidate_dirs(repo_root: Path) -> list[Path]:
    dirs = [Path(d) for d in os.environ.get("PATH", "").split(os.pathsep) if d]
    return [*dirs, repo_root / "node_modules" / ".bin"]


def _own_doctor(who: Identity) -> Path | None:
    """The real path of the running entry point's sibling doctor of `who`; None when it is not a file."""
    try:
        doctor = (Path(sys.argv[0]).resolve().parent / who.doctor).resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    return doctor if doctor.is_file() else None


def _is_own(doctor: Path, own: Path | None) -> bool:
    try:
        return own is not None and doctor.resolve(strict=True) == own
    except (OSError, RuntimeError):
        return False


def _discover_dir(lang: str, repo_root: Path, who: Identity) -> Path | None:
    """The first directory (each real path once, never our own) whose executable doctor of `who` qualifies."""
    own = _own_doctor(who)
    probed: set[Path] = set()
    for directory in _candidate_dirs(repo_root):
        try:
            real = directory.resolve()
        except (OSError, RuntimeError):
            continue
        if real in probed:
            continue
        probed.add(real)
        doctor = directory / who.doctor
        if _is_own(doctor, own):
            continue
        if doctor.is_file() and os.access(doctor, os.X_OK) and _qualifies([str(doctor), "--twin"], lang, who):
            return directory
    return None


def _launcher(lang: str, repo_root: Path, who: Identity) -> _Launcher:
    """How to run `who`'s `lang` twin's commands; TwinError when no twin qualifies."""
    directory = _discover_dir(lang, repo_root, who)
    if directory is not None:
        return _Launcher(directory, [])
    runner = shlex.split(render_template(language(lang)["runner"], {"package": who.package, "version": who.version}))
    if shutil.which(runner[0]) is not None and _qualifies([*runner, who.doctor, "--twin"], lang, who):
        return _Launcher(None, runner)
    raise TwinError(_hint("twin.unavailable", lang, who))


def refuse_if_forwarded(lang: str) -> None:
    if os.environ.get(FORWARDED_ENV) == "1":
        raise TwinError(message("twin.forward-refused", language=lang))


def _identity_ok(document: dict[str, Any], lang: str, who: Identity) -> bool:
    expected = (lang, who.version, who.hashes[0])
    return (document["language"], document["version"], document["contract_hash"]) == expected


def _document(
    proc: subprocess.CompletedProcess[bytes], schema_name: str, lang: str, who: Identity
) -> dict[str, Any] | None:
    """The run's stdout as a document of `who`'s `lang` twin, valid against `who`'s schema; RelayedFailure on a
    non-zero exit."""
    if proc.returncode > 0:
        raise RelayedFailure
    try:
        document = json.loads(proc.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(document, dict) or proc.returncode < 0:
        return None
    if validate(who.contract.schema(schema_name), document, (who.contract,)):
        return None
    return document if _identity_ok(document, lang, who) else None


def _run(
    lang: str, command: str, argv: list[str], *, cwd: Path | None = None, stdin: bytes | None = None, capture: bool = False
) -> subprocess.CompletedProcess[bytes]:
    """`argv`, the `lang` twin's `command`; TwinError when it cannot start."""
    stdout = subprocess.PIPE if capture else None
    try:
        return subprocess.run(argv, input=stdin, stdout=stdout, cwd=cwd, env=_env(), check=False)
    except OSError as exc:
        raise TwinError(message("twin.launch-failed", language=lang, command=command)) from exc


def request_document(
    lang: str,
    who: Identity,
    command: str,
    args: list[str],
    schema_name: str,
    *,
    repo_root: Path,
    cwd: Path | None = None,
    stdin: bytes | None = None,
    accept: Callable[[dict[str, Any]], bool] = lambda _document: True,
) -> dict[str, Any]:
    """`command ARGS` in `who`'s `lang` twin: its stdout as one document valid against `who`'s schema `schema_name`
    that `accept` takes; RelayedFailure when the run fails, TwinError otherwise."""
    refuse_if_forwarded(lang)
    argv = [*_launcher(lang, repo_root, who).argv(command), *args]
    sys.stdout.flush()
    sys.stderr.flush()
    document = _document(_run(lang, command, argv, cwd=cwd, stdin=stdin, capture=True), schema_name, lang, who)
    if document is None or not accept(document):
        raise TwinError(_hint(_FACTS_INVALID, lang, who))
    return document


def run_language(
    command: str, lang: str, args: list[str], *, cwd: Path, repo_root: Path, who: Identity | None = None
) -> int:
    """`command --language lang ARGS` in `who`'s (default: dr's) `lang` twin, streams relayed; its exit code (a
    signal: 2)."""
    refuse_if_forwarded(lang)
    argv = [*_launcher(lang, repo_root, who or dr_identity()).argv(command), "--language", lang, *args]
    sys.stdout.flush()
    sys.stderr.flush()
    code = _run(lang, command, argv, cwd=cwd).returncode
    return code if code >= 0 else 2


def forward(command: str, lang: str, argv: list[str], *, repo_root: Path, who: Identity | None = None) -> int:
    """`command ARGV` in `who`'s (default: dr's) `lang` twin from the current directory, streams relayed; its exit
    code (a signal: 128+N)."""
    refuse_if_forwarded(lang)
    sys.stdout.flush()
    sys.stderr.flush()
    code = _run(lang, command, [*_launcher(lang, repo_root, who or dr_identity()).argv(command), *argv]).returncode
    return code if code >= 0 else 128 - code


def run_captured(
    command: str, lang: str, args: list[str], *, repo_root: Path, who: Identity | None = None
) -> tuple[int, bytes]:
    """`command ARGS` in `who`'s (default: dr's) `lang` twin from the current directory: its exit code (a signal: 2)
    and stdout; stderr relayed."""
    refuse_if_forwarded(lang)
    sys.stdout.flush()
    sys.stderr.flush()
    argv = [*_launcher(lang, repo_root, who or dr_identity()).argv(command), *args]
    proc = _run(lang, command, argv, capture=True)
    return (proc.returncode if proc.returncode >= 0 else 2), proc.stdout
