import importlib
import tomllib
from pathlib import Path

import pytest

from living_architecture import shims
from living_architecture.config import CONFIG_FILENAME

REPO_ROOT = Path(__file__).resolve().parent.parent


class Execd(Exception):
    pass


@pytest.fixture
def execvp(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake(file: str, args: list[str]) -> None:
        calls.append(args)
        raise Execd

    monkeypatch.setattr(shims.os, "execvp", fake)
    return calls


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _enable_coderabbit(repo: Path) -> None:
    (repo / CONFIG_FILENAME).write_text("reviewers: {coderabbit: true}\n", encoding="utf-8")


@pytest.mark.parametrize("shim", [shims.fetch_coderabbit_threads, shims.reply_invalid_coderabbit])
def test_coderabbit_commands_refuse_when_disabled(repo, execvp, shim, capsys):
    with pytest.raises(SystemExit) as exc:
        shim(["7"])
    assert exc.value.code == 3
    assert "reviewers.coderabbit" in capsys.readouterr().err
    assert execvp == []


@pytest.mark.parametrize(
    ("shim", "script"),
    [(shims.fetch_coderabbit_threads, "fetch-coderabbit-threads.sh"),
     (shims.reply_invalid_coderabbit, "reply-invalid-coderabbit.sh")],
)
def test_coderabbit_commands_run_when_enabled(repo, execvp, shim, script):
    _enable_coderabbit(repo)
    with pytest.raises(Execd):
        shim(["7", "--repo", "o/r"])
    assert execvp == [["bash", str(shims.SCRIPTS_DIR / script), "7", "--repo", "o/r"]]


@pytest.mark.parametrize(
    ("shim", "script"),
    [(shims.reply_to_pr_thread, "reply-to-pr-thread.sh"),
     (shims.fetch_failed_pr_checks, "fetch-failed-pr-checks.sh")],
)
def test_ungated_commands(repo, execvp, shim, script):
    with pytest.raises(Execd):
        shim(["x"])
    assert execvp == [["bash", str(shims.SCRIPTS_DIR / script), "x"]]


def test_wait_skips_coderabbit_when_disabled(repo, execvp):
    with pytest.raises(Execd):
        shims.wait_for_reviews(["7"])
    assert execvp[0][-2:] == ["7", "--skip-coderabbit"]


def test_wait_waits_for_coderabbit_when_enabled(repo, execvp):
    _enable_coderabbit(repo)
    with pytest.raises(Execd):
        shims.wait_for_reviews(["7"])
    assert execvp[0][-1] == "7"


def test_invalid_config_exits_2(repo, execvp, capsys):
    (repo / CONFIG_FILENAME).write_text("bogus: 1\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        shims.wait_for_reviews(["7"])
    assert exc.value.code == 2
    assert execvp == []


def test_every_bundled_script_has_an_entry_point():
    scripts = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    shimmed = {f"{target.split(':')[1].replace('_', '-')}.sh" for target in scripts.values()
               if target.startswith("living_architecture.shims:")}
    assert shimmed == {p.name for p in shims.SCRIPTS_DIR.glob("*.sh")}


def test_every_entry_point_resolves():
    scripts = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    for name, target in scripts.items():
        module, func = target.split(":")
        assert callable(getattr(importlib.import_module(module), func)), name
