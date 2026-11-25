"""Twin discovery: the invoking twin's own doctor is never probed; without one, nothing is skipped."""

import os
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Any

import pytest

from trmv import twin

VENV_BIN = Path(sysconfig.get_path("scripts"))
OWN_ENTRY = VENV_BIN / "trmv-refactor"
OWN_DOCTOR = VENV_BIN / "trmv-doctor"
TRMV = twin.trmv_identity()
TYPESCRIPT_IDENTITY = TRMV.line("typescript")


def _stub_twin(directory: Path) -> Path:
    """A directory whose `trmv-doctor --twin` qualifies as trmv's TypeScript twin."""
    directory.mkdir(parents=True)
    doctor = directory / "trmv-doctor"
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
    return [Path(argv[0]).resolve() for argv in spawns if Path(argv[0]).name == "trmv-doctor"]


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
        (own_dir / "trmv-doctor").symlink_to(OWN_DOCTOR)
    stub = _stub_twin(tmp_path / "stub")
    _use(monkeypatch, OWN_ENTRY, [own_dir, stub])
    assert twin._discover_dir("typescript", tmp_path, TRMV) == stub
    assert OWN_DOCTOR.resolve() not in _doctor_spawns(spawns)
    assert (stub / "trmv-doctor").resolve() in _doctor_spawns(spawns)


def test_own_doctor_is_skipped_even_if_it_would_qualify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spawns: list[list[str]]
) -> None:
    own = _stub_twin(tmp_path / "own")
    (own / "trmv-refactor").write_text("")
    other = _stub_twin(tmp_path / "other")
    _use(monkeypatch, own / "trmv-refactor", [own, other])
    assert twin._discover_dir("typescript", tmp_path, TRMV) == other
    assert (own / "trmv-doctor").resolve() not in _doctor_spawns(spawns)


@pytest.mark.parametrize("sibling", ["missing", "dangling", "directory"])
def test_without_an_own_doctor_nothing_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, spawns: list[list[str]], sibling: str
) -> None:
    own = tmp_path / "own"
    own.mkdir()
    (own / "trmv-refactor").write_text("")
    if sibling == "dangling":
        (own / "trmv-doctor").symlink_to(tmp_path / "nowhere")
    elif sibling == "directory":
        (own / "trmv-doctor").mkdir()
    first = _stub_twin(tmp_path / "first")
    second = _stub_twin(tmp_path / "second")
    _use(monkeypatch, own / "trmv-refactor", [own, first, second])
    assert twin._discover_dir("typescript", tmp_path, TRMV) == first
    assert _doctor_spawns(spawns) == [(first / "trmv-doctor").resolve()]
