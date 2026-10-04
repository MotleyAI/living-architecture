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


def _invalid_config(repo: Path) -> None:
    (repo / CONFIG_FILENAME).write_text("bogus: 1\n", encoding="utf-8")


def _removed_coderabbit_key(repo: Path) -> None:
    (repo / CONFIG_FILENAME).write_text("reviewers: {coderabbit: false}\n", encoding="utf-8")


# The config-free review shims, by entry-point name (resolved lazily, so one missing entry fails alone).
CONFIG_FREE = [
    ("la_fetch_coderabbit_threads", "fetch-coderabbit-threads.sh"),
    ("la_reply_invalid_coderabbit", "reply-invalid-coderabbit.sh"),
    ("la_reply_to_pr_thread", "reply-to-pr-thread.sh"),
    ("la_fetch_failed_pr_checks", "fetch-failed-pr-checks.sh"),
    ("la_wait_for_reviews", "wait-for-reviews.sh"),
]


# These helpers run whatever the repo config says (or whether it exists, or parses), argv unchanged.
@pytest.mark.parametrize("setup", [lambda repo: None, _removed_coderabbit_key, _invalid_config],
                         ids=["no-config", "removed-coderabbit-key", "invalid-config"])
@pytest.mark.parametrize(("shim", "script"), CONFIG_FREE)
def test_config_free_commands(repo, execvp, shim, script, setup):
    setup(repo)
    with pytest.raises(Execd):
        getattr(cli, shim)(["7", "--repo", "o/r"])
    assert execvp == [["bash", str(SCRIPTS_DIR / script), "7", "--repo", "o/r"]]


@pytest.mark.parametrize(("shim", "script"), CONFIG_FREE)
def test_config_free_commands_run_outside_a_git_repo(tmp_path, monkeypatch, execvp, shim, script):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(Execd):
        getattr(cli, shim)(["7"])
    assert execvp == [["bash", str(SCRIPTS_DIR / script), "7"]]


def test_no_command_has_a_gate():
    assert [name for name, spec in manifest().items() if "gate" in spec] == []
    assert "gate" not in (snapshot_dir() / "cli.yaml").read_text(encoding="utf-8").split("\ncommands:")[0]


def test_pr_reviewers_runs_its_bundled_script():
    assert manifest()["la-pr-reviewers"]["script"] == "pr-reviewers.sh"
    assert (SCRIPTS_DIR / "pr-reviewers.sh").is_file()


def test_every_manifest_command_has_an_entry_point():
    scripts = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    assert sorted(set(manifest()) - set(scripts)) == []


def test_every_bundled_script_has_a_command():
    shimmed = {spec["script"] for spec in manifest().values() if "script" in spec}
    assert shimmed == {p.name for p in SCRIPTS_DIR.glob("*.sh")}


def test_every_entry_point_resolves():
    scripts = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["scripts"]
    for name, target in scripts.items():
        module, func = target.split(":")
        assert callable(getattr(importlib.import_module(module), func)), name
