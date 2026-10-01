import importlib
import tomllib
from pathlib import Path

import pytest

from living_architecture import cli, review
from living_architecture.config import CONFIG_FILENAME
from living_architecture.contract import manifest, snapshot_dir

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = snapshot_dir() / "scripts"


class Execd(Exception):
    pass


@pytest.fixture
def execvp(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake(file: str, args: list[str]) -> None:
        calls.append(args)
        raise Execd

    monkeypatch.setattr(review.os, "execvp", fake)
    return calls


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _enable_coderabbit(repo: Path) -> None:
    (repo / CONFIG_FILENAME).write_text("reviewers: {coderabbit: true}\n", encoding="utf-8")


def _disable_coderabbit(repo: Path) -> None:
    (repo / CONFIG_FILENAME).write_text("reviewers: {coderabbit: false}\n", encoding="utf-8")


def _invalid_config(repo: Path) -> None:
    (repo / CONFIG_FILENAME).write_text("bogus: 1\n", encoding="utf-8")


UNGATED = [
    (cli.la_fetch_coderabbit_threads, "fetch-coderabbit-threads.sh"),
    (cli.la_reply_invalid_coderabbit, "reply-invalid-coderabbit.sh"),
    (cli.la_reply_to_pr_thread, "reply-to-pr-thread.sh"),
    (cli.la_fetch_failed_pr_checks, "fetch-failed-pr-checks.sh"),
]


# Single-source helpers run whatever the repo config says (or whether it exists, or parses).
@pytest.mark.parametrize("setup", [lambda repo: None, _enable_coderabbit, _disable_coderabbit, _invalid_config],
                         ids=["no-config", "coderabbit-on", "coderabbit-off", "invalid-config"])
@pytest.mark.parametrize(("shim", "script"), UNGATED)
def test_ungated_commands(repo, execvp, shim, script, setup):
    setup(repo)
    with pytest.raises(Execd):
        shim(["7", "--repo", "o/r"])
    assert execvp == [["bash", str(SCRIPTS_DIR / script), "7", "--repo", "o/r"]]


@pytest.mark.parametrize(("shim", "script"), UNGATED)
def test_ungated_commands_run_outside_a_git_repo(tmp_path, monkeypatch, execvp, shim, script):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(Execd):
        shim(["7"])
    assert execvp == [["bash", str(SCRIPTS_DIR / script), "7"]]


def test_wait_skips_coderabbit_when_disabled(repo, execvp):
    with pytest.raises(Execd):
        cli.la_wait_for_reviews(["7"])
    assert execvp[0][-2:] == ["7", "--skip-coderabbit"]


def test_wait_waits_for_coderabbit_when_enabled(repo, execvp):
    _enable_coderabbit(repo)
    with pytest.raises(Execd):
        cli.la_wait_for_reviews(["7"])
    assert execvp[0][-1] == "7"


def test_invalid_config_exits_2(repo, execvp, capsys):
    _invalid_config(repo)
    with pytest.raises(SystemExit) as exc:
        cli.la_wait_for_reviews(["7"])
    assert exc.value.code == 2
    assert execvp == []


def test_every_bundled_script_has_a_command():
    shimmed = {spec["script"] for spec in manifest().values() if "script" in spec}
    assert shimmed == {p.name for p in SCRIPTS_DIR.glob("*.sh")}


def test_every_entry_point_resolves():
    scripts = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    for name, target in scripts.items():
        module, func = target.split(":")
        assert callable(getattr(importlib.import_module(module), func)), name
