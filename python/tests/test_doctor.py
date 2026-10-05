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
    (tmp_path / CONFIG_FILENAME).write_text("tracker: jira\n", encoding="utf-8")
    assert cli.la_doctor(["--root", str(tmp_path)]) == 1
    assert "FAIL:" in capsys.readouterr().out


def test_missing_executable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda exe: None if exe == "gh" else "/bin/x")
    assert doctor.run_checks(root=tmp_path, expect=None) == ["`gh` not found on PATH"]


def test_twin_identity_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli.la_doctor(["--twin"]) == 0
    assert capsys.readouterr().out == f"python {__version__} {contract_hash()}\n"


MISSING_CONFIG = "FAIL: no living-architecture.yaml at the repo root; run /la:init to onboard this repo"
OPENSPEC_ABSENT = (
    "FAIL: openspec is true but the repo has no openspec/ directory; run /la:openspec-init or set openspec: false"
)
OPENSPEC_PRESENT = (
    "FAIL: openspec is false but the repo has an openspec/ directory; set openspec: true or remove the directory"
)
ARCHITECTURE_ABSENT = (
    "FAIL: architecture is true but the repo has no architecture/index.yaml; run /la:arch-init or set architecture: false"
)
ARCHITECTURE_PRESENT = (
    "FAIL: architecture is false but the repo has architecture/index.yaml; set architecture: true or remove the file"
)
NO_PLAN_STORE = (
    "FAIL: tracker is none and openspec is false, so no plan survives a session reset; set a tracker or openspec: true"
)


def _doctor(root: Path, capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, list[str]]:
    code = cli.la_doctor(["--root", str(root), *args])
    return code, capsys.readouterr().out.splitlines()


@pytest.mark.usefixtures("all_tools")
def test_require_config_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _doctor(tmp_path, capsys, "--require-config") == (1, [MISSING_CONFIG])


@pytest.mark.usefixtures("all_tools")
def test_require_config_present(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / CONFIG_FILENAME).write_text("openspec: false\n", encoding="utf-8")
    code, out = _doctor(tmp_path, capsys, "--require-config")
    assert code == 0
    assert out == [f"ok: la tools {__version__}; config from {CONFIG_FILENAME}"]


@pytest.mark.usefixtures("all_tools")
def test_missing_config_without_flag_is_healthy(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = _doctor(tmp_path, capsys)
    assert code == 0
    assert out == [f"ok: la tools {__version__}; config from defaults (no config file)"]


@pytest.mark.usefixtures("all_tools")
@pytest.mark.parametrize(
    ("config", "dirs", "files", "expected"),
    [
        ("openspec: true\n", [], [], [OPENSPEC_ABSENT]),
        ("openspec: false\n", ["openspec"], [], [OPENSPEC_PRESENT]),
        ("openspec: false\narchitecture: true\n", [], [], [ARCHITECTURE_ABSENT]),
        ("openspec: false\narchitecture: false\n", [], ["architecture/index.yaml"], [ARCHITECTURE_PRESENT]),
        ("openspec: false\narchitecture: false\n", [], ["architecture/notes.md"], []),
        ("tracker: none\nopenspec: false\n", [], [], [NO_PLAN_STORE]),
        ("openspec: true\narchitecture: true\n", [], [], [OPENSPEC_ABSENT, ARCHITECTURE_ABSENT]),
        ("tracker: none\nopenspec: false\narchitecture: true\n", ["openspec"], [],
         [OPENSPEC_PRESENT, ARCHITECTURE_ABSENT, NO_PLAN_STORE]),
    ],
)
def test_config_disk_consistency(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    config: str,
    dirs: list[str],
    files: list[str],
    expected: list[str],
) -> None:
    (tmp_path / CONFIG_FILENAME).write_text(config, encoding="utf-8")
    for d in dirs:
        (tmp_path / d).mkdir()
    for f in files:
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f).write_text("x: 1\n", encoding="utf-8")
    code, out = _doctor(tmp_path, capsys)
    assert code == (1 if expected else 0)
    assert [line for line in out if line.startswith("FAIL:")] == expected


@pytest.mark.usefixtures("all_tools")
def test_no_file_skips_consistency(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "architecture").mkdir()
    (tmp_path / "architecture" / "index.yaml").write_text("x: 1\n", encoding="utf-8")
    assert _doctor(tmp_path, capsys)[0] == 0
