from pathlib import Path

import pytest

from living_architecture import __version__, cli, doctor
from living_architecture.config import CONFIG_FILENAME
from living_architecture.contract import contract_hash


@pytest.fixture
def all_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda exe: f"/usr/bin/{exe}")


@pytest.mark.usefixtures("all_tools")
def test_healthy(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.la_doctor(["--root", str(tmp_path), "--expect", __version__]) == 0
    assert "defaults (no config file)" in capsys.readouterr().out


@pytest.mark.usefixtures("all_tools")
def test_version_mismatch(tmp_path: Path) -> None:
    problems = doctor.run_checks(root=tmp_path, expect="0.0.0-other")
    assert len(problems) == 1
    assert "expects 0.0.0-other" in problems[0]


@pytest.mark.usefixtures("all_tools")
def test_no_expect_skips_version_check(tmp_path: Path) -> None:
    assert doctor.run_checks(root=tmp_path, expect=None) == []


@pytest.mark.usefixtures("all_tools")
def test_invalid_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / CONFIG_FILENAME).write_text("reviewers: {sonar: {enabled: true}}\n", encoding="utf-8")
    assert cli.la_doctor(["--root", str(tmp_path)]) == 1
    assert "FAIL:" in capsys.readouterr().out


def test_missing_executable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda exe: None if exe == "gh" else "/bin/x")
    assert doctor.run_checks(root=tmp_path, expect=None) == ["`gh` not found on PATH"]


def test_twin_identity_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli.la_doctor(["--twin"]) == 0
    assert capsys.readouterr().out == f"python {__version__} {contract_hash()}\n"
