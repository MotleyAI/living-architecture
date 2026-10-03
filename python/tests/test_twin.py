"""Twin discovery: the invoking twin's own `la-doctor` is never probed; without one, nothing is skipped."""

import os
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Any

import pytest

from living_architecture import __version__, twin
from living_architecture.contract import contract_hash

VENV_BIN = Path(sysconfig.get_path("scripts"))
OWN_ENTRY = VENV_BIN / "la-arch-check"
OWN_DOCTOR = VENV_BIN / "la-doctor"
TYPESCRIPT_IDENTITY = f"typescript {__version__} {contract_hash()}"


def _stub_twin(directory: Path) -> Path:
    """A directory whose `la-doctor --twin` qualifies as the TypeScript twin."""
    directory.mkdir(parents=True)
    doctor = directory / "la-doctor"
    doctor.write_text(f"#!/bin/sh\necho '{TYPESCRIPT_IDENTITY}'\n")
    doctor.chmod(0o755)
    return directory


@pytest.fixture
def spawns(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Every argv the twin module runs, recorded before the real run."""
    calls: list[list[str]] = []
    real_run = subprocess.run

    def record(argv: list[str], *args: Any, **kwargs: Any) -> Any:
        calls.append([str(a) for a in argv])
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(twin.subprocess, "run", record)
    return calls


def _doctor_spawns(spawns: list[list[str]]) -> list[Path]:
    return [Path(argv[0]).resolve() for argv in spawns if Path(argv[0]).name == "la-doctor"]


def _use(monkeypatch: pytest.MonkeyPatch, entry: Path, path: list[Path]) -> None:
    monkeypatch.setattr(sys, "argv", [str(entry)])
    monkeypatch.setenv("PATH", os.pathsep.join(str(p) for p in path))


@pytest.mark.parametrize("via_symlink_dir", [False, True], ids=["bin-dir", "symlink-dir"])
def test_own_install_is_not_probed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spawns: list[list[str]], via_symlink_dir: bool
) -> None:
    own_dir = VENV_BIN
    if via_symlink_dir:
        own_dir = tmp_path / "links"
        own_dir.mkdir()
        (own_dir / "la-doctor").symlink_to(OWN_DOCTOR)
    stub = _stub_twin(tmp_path / "stub")
    _use(monkeypatch, OWN_ENTRY, [own_dir, stub])
    assert twin._discover_dir("typescript", tmp_path) == stub
    assert OWN_DOCTOR.resolve() not in _doctor_spawns(spawns)
    assert (stub / "la-doctor").resolve() in _doctor_spawns(spawns)


def test_own_doctor_is_skipped_even_if_it_would_qualify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spawns: list[list[str]]
) -> None:
    own = _stub_twin(tmp_path / "own")
    (own / "la-arch-check").write_text("")
    other = _stub_twin(tmp_path / "other")
    _use(monkeypatch, own / "la-arch-check", [own, other])
    assert twin._discover_dir("typescript", tmp_path) == other
    assert (own / "la-doctor").resolve() not in _doctor_spawns(spawns)


@pytest.mark.parametrize("sibling", ["missing", "dangling", "directory"])
def test_without_an_own_doctor_nothing_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spawns: list[list[str]], sibling: str
) -> None:
    own = tmp_path / "own"
    own.mkdir()
    (own / "la-arch-check").write_text("")
    if sibling == "dangling":
        (own / "la-doctor").symlink_to(tmp_path / "nowhere")
    elif sibling == "directory":
        (own / "la-doctor").mkdir()
    first = _stub_twin(tmp_path / "first")
    second = _stub_twin(tmp_path / "second")
    _use(monkeypatch, own / "la-arch-check", [own, first, second])
    assert twin._discover_dir("typescript", tmp_path) == first
    assert _doctor_spawns(spawns) == [(first / "la-doctor").resolve()]
