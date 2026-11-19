import os
import subprocess
from pathlib import Path

import pytest

from deterministic_refactor import config as la_config
from deterministic_refactor.contract import contract_hash as dr_contract_hash
from living_architecture import __version__, doctor
from living_architecture.cli.la_doctor import la_doctor
from living_architecture.contract import config_file, contract_hash


def _declared(text: str) -> str:
    """`text` as a committed config declaring the current format."""
    return f"format: {la_config.current_format(config_file())}\n{text}"


@pytest.fixture(autouse=True)
def dr_installed(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """A matching dr installation, except for the tests of the dr check itself (marked `dr_check`)."""
    if request.node.get_closest_marker("dr_check") is None:
        monkeypatch.setattr(doctor, "_dr_problem", lambda: None)


@pytest.fixture
def all_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda exe: f"/usr/bin/{exe}")


@pytest.mark.usefixtures("all_tools")
def test_healthy(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert la_doctor(["--root", str(tmp_path)]) == 0
    assert "defaults (no config file)" in capsys.readouterr().out


def _plugin(root: Path, version: str) -> str:
    """A plugin dir whose plugin.json declares `version`."""
    (root / "plugin" / ".claude-plugin").mkdir(parents=True)
    (root / "plugin" / ".claude-plugin" / "plugin.json").write_text(f'{{"version": "{version}"}}', encoding="utf-8")
    return str(root / "plugin")


@pytest.mark.usefixtures("all_tools")
@pytest.mark.parametrize("plugin_version", ["1.2.0", "1.2.3rc1", "01.002.9-rc.1"])
def test_prerelease_installed_version_matches_its_series(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, plugin_version: str
) -> None:
    monkeypatch.setattr(doctor, "__version__", "1.2.3rc1")
    assert doctor.run_checks(root=tmp_path, plugin=_plugin(tmp_path, plugin_version)) == []


@pytest.mark.usefixtures("all_tools")
def test_prerelease_installed_version_reports_another_series(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "__version__", "1.2.3rc1")
    mismatch = (
        "installed la tools are 1.2.3rc1, but plugin 1.3.0 needs 1.3.x;"
        " reinstall them with: uv tool install living-architecture==1.3.0 --with-executables-from deterministic-refactor"
    )
    assert doctor.run_checks(root=tmp_path, plugin=_plugin(tmp_path, "1.3.0")) == [mismatch]


@pytest.mark.usefixtures("all_tools")
def test_invalid_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / config_file()).write_text(_declared("tracker: jira\n"), encoding="utf-8")
    assert la_doctor(["--root", str(tmp_path)]) == 1
    assert "FAIL:" in capsys.readouterr().out


def test_missing_executable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda exe: None if exe == "gh" else "/bin/x")
    assert doctor.run_checks(root=tmp_path) == ["`gh` not found on PATH"]


def test_twin_identity_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.chdir(tmp_path)
    assert la_doctor(["--twin"]) == 0
    assert capsys.readouterr().out == f"python {__version__} {contract_hash()} {dr_contract_hash()}\n"


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
    code = la_doctor(["--root", str(root), *args])
    return code, capsys.readouterr().out.splitlines()


@pytest.mark.usefixtures("all_tools")
def test_require_config_missing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _doctor(tmp_path, capsys, "--require-config") == (1, [MISSING_CONFIG])


@pytest.mark.usefixtures("all_tools")
def test_require_config_present(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / config_file()).write_text(_declared("openspec: false\n"), encoding="utf-8")
    code, out = _doctor(tmp_path, capsys, "--require-config")
    assert code == 0
    assert out == [f"ok: la tools {__version__}; config from {config_file()}"]


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
    (tmp_path / config_file()).write_text(_declared(config), encoding="utf-8")
    for d in dirs:
        (tmp_path / d).mkdir()
    for f in files:
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f).write_text("x: 1\n", encoding="utf-8")
    code, out = _doctor(tmp_path, capsys, "--require-plan-store")
    assert code == (1 if expected else 0)
    assert [line for line in out if line.startswith("FAIL:")] == expected


@pytest.mark.usefixtures("all_tools")
def test_plan_store_not_required_without_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / config_file()).write_text(_declared("tracker: none\nopenspec: false\n"), encoding="utf-8")
    assert _doctor(tmp_path, capsys, "--require-config")[0] == 0


@pytest.mark.usefixtures("all_tools")
def test_no_file_skips_consistency(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "architecture").mkdir()
    (tmp_path / "architecture" / "index.yaml").write_text("x: 1\n", encoding="utf-8")
    assert _doctor(tmp_path, capsys)[0] == 0


# ---- living-architecture.local.yaml

LOCAL = "living-architecture.local.yaml"
LOCAL_TRACKED = (
    f"FAIL: {LOCAL} is tracked by git, but it holds one contributor's overrides;"
    f" run git rm --cached {LOCAL} and add it to .gitignore"
)
LOCAL_NOT_IGNORED = f"FAIL: {LOCAL} is not git-ignored; add it to .gitignore"
LOCAL_GIT_FAILED = f"FAIL: git failed, so whether {LOCAL} is git-ignored cannot be checked"


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=root, check=True, capture_output=True,
    )


def _repo(root: Path, *, local: str | None = "tracker: github\n", ignored: bool = False) -> Path:
    _git(root, "init", "-q", "-b", "main")
    if ignored:
        (root / ".gitignore").write_text(f"{LOCAL}\n", encoding="utf-8")
    if local is not None:
        (root / LOCAL).write_text(local, encoding="utf-8")
    return root


def _fake_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, script: str) -> None:
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    git = bin_dir / "git"
    git.write_text(f"#!/bin/sh\n{script}", encoding="utf-8")
    git.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


@pytest.mark.usefixtures("all_tools")
def test_local_ignored_is_a_second_source(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, ignored=True)
    (root / config_file()).write_text(_declared("openspec: false\n"), encoding="utf-8")
    assert _doctor(root, capsys) == (0, [f"ok: la tools {__version__}; config from {config_file()} + {LOCAL}"])


@pytest.mark.usefixtures("all_tools")
def test_local_outside_git_follows_the_defaults_source(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / LOCAL).write_text("tracker: github\n", encoding="utf-8")
    assert _doctor(tmp_path, capsys) == (0, [f"ok: la tools {__version__}; config from defaults (no config file) + {LOCAL}"])


@pytest.mark.usefixtures("all_tools")
def test_local_committed_is_tracked(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path)
    _git(root, "add", LOCAL)
    _git(root, "commit", "-q", "-m", "init")
    assert _doctor(root, capsys) == (1, [LOCAL_TRACKED])


@pytest.mark.usefixtures("all_tools")
def test_local_staged_is_tracked_even_when_ignored(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path)
    _git(root, "add", LOCAL)
    (root / ".gitignore").write_text(f"{LOCAL}\n", encoding="utf-8")
    assert _doctor(root, capsys) == (1, [LOCAL_TRACKED])


@pytest.mark.usefixtures("all_tools")
def test_local_not_ignored(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _doctor(_repo(tmp_path), capsys) == (1, [LOCAL_NOT_IGNORED])


@pytest.mark.usefixtures("all_tools")
def test_local_ls_files_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path)
    (root / ".git" / "index").write_text("not an index\n", encoding="utf-8")
    assert _doctor(root, capsys) == (1, [LOCAL_GIT_FAILED])


@pytest.mark.usefixtures("all_tools")
@pytest.mark.parametrize("status", [2, 128])
def test_local_check_ignore_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], status: int
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _repo(root)
    _fake_git(tmp_path, monkeypatch, f'for a in "$@"; do [ "$a" = check-ignore ] && exit {status}; done\nexit 0\n')
    assert _doctor(root, capsys) == (1, [LOCAL_GIT_FAILED])


@pytest.mark.usefixtures("all_tools")
def test_no_local_file_runs_no_local_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _repo(root, local=None)
    _fake_git(tmp_path, monkeypatch, "exit 128\n")
    assert _doctor(root, capsys)[0] == 0


@pytest.mark.usefixtures("all_tools")
def test_local_not_git_runs_no_local_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / LOCAL).write_text("tracker: github\n", encoding="utf-8")
    _fake_git(tmp_path, monkeypatch, "exit 128\n")
    assert _doctor(root, capsys)[0] == 0


def test_local_finding_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda exe: None if exe == "gh" else f"/usr/bin/{exe}")
    root = _repo(tmp_path, local="tracker: none\n")
    (root / config_file()).write_text(_declared("openspec: false\n"), encoding="utf-8")
    assert _doctor(root, capsys, "--require-plan-store") == (1, [NO_PLAN_STORE, LOCAL_NOT_IGNORED, "FAIL: `gh` not found on PATH"])


@pytest.mark.usefixtures("all_tools")
def test_local_takes_part_in_consistency(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, local="tracker: none\n", ignored=True)
    (root / config_file()).write_text(_declared("openspec: false\n"), encoding="utf-8")
    assert _doctor(root, capsys, "--require-plan-store") == (1, [NO_PLAN_STORE])


@pytest.mark.usefixtures("all_tools")
def test_local_alone_skips_consistency(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, local="tracker: none\n", ignored=True)
    assert _doctor(root, capsys)[0] == 0


@pytest.mark.usefixtures("all_tools")
def test_require_config_ignores_a_local_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, ignored=True)
    assert _doctor(root, capsys, "--require-config") == (1, [MISSING_CONFIG])


@pytest.mark.usefixtures("all_tools")
def test_invalid_local_without_committed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, local="openspec: false\n", ignored=True)
    code, out = _doctor(root, capsys)
    assert code == 1
    [line] = out
    assert line.startswith("FAIL: ")
    assert "openspec" in line
    assert LOCAL in line


@pytest.mark.usefixtures("all_tools")
def test_require_config_still_validates_a_local_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, local="openspec: false\n", ignored=True)
    code, out = _doctor(root, capsys, "--require-config")
    assert code == 1
    missing, invalid = out
    assert missing == MISSING_CONFIG
    assert "openspec" in invalid
    assert LOCAL in invalid


def _fake_dr_doctor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, line: str) -> None:
    """A `dr-doctor` first on PATH whose `--twin` prints `line`."""
    bin_dir = tmp_path / "dr-bin"
    bin_dir.mkdir()
    fake = bin_dir / "dr-doctor"
    fake.write_text(f"#!/bin/sh\necho '{line}'\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


def _dr_line(version: str) -> str:
    return f"python {version} {dr_contract_hash()}"


@pytest.mark.dr_check
def test_matching_dr_installation_is_healthy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_dr_doctor(tmp_path, monkeypatch, _dr_line(__version__))
    assert doctor._dr_problem() is None


@pytest.mark.dr_check
def test_missing_dr_installation_names_the_install_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda exe: None if exe == "dr-doctor" else f"/usr/bin/{exe}")
    problem = doctor._dr_problem()
    assert problem is not None
    assert f"uv tool install living-architecture=={__version__} --with-executables-from deterministic-refactor" in problem


@pytest.mark.dr_check
def test_other_dr_version_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_dr_doctor(tmp_path, monkeypatch, _dr_line("0.11.0"))
    problem = doctor._dr_problem()
    assert problem is not None
    assert "0.11.0" in problem
    assert __version__ in problem


@pytest.mark.usefixtures("all_tools")
def test_both_config_files_are_reported_once(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / config_file()).write_text(_declared("tracker: jira\n"), encoding="utf-8")
    (tmp_path / "deterministic-refactor.yaml").write_text("format: 9.9.9\n", encoding="utf-8")
    assert la_doctor(["--root", str(tmp_path)]) == 1
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert "deterministic-refactor.yaml" in lines[0]
    assert config_file() in lines[0]
