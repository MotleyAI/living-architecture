"""The leak-token matcher and the token list of stealth mode."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from living_architecture.leaks import find_tokens, leak_tokens

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir())
CORE = ["living-architecture", "type-rename-move", "trmv", "/la:", "/trmv:", "ALLOW("]
WAIVABLE = ["arc42", "LikeC4", "OpenSpec", "reset point", "decisions log", "pr-plan", "pr-tests", "pr-implement",
            "pr-review"]
REGISTRY = ["living-architecture.yaml", "living-architecture.local.yaml", "architecture/index.yaml", "trmv.yaml",
            ".tsc-baseline.json", ".basedpyright/baseline.json"]
TOKENS = [*CORE, *WAIVABLE, *REGISTRY, "la-doctor", "trmv-typecheck"]


def _commands(package: str) -> list[str]:
    return list(yaml.safe_load((REPO_ROOT / "shared" / package / "cli.yaml").read_text(encoding="utf-8"))["commands"])


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    if files:
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init"], cwd=tmp_path,
                       check=True)
    return tmp_path


@pytest.mark.parametrize(
    ("line", "hits"),
    [
        ("Ran **LA-DOCTOR**, then the `trmv-typecheck` gate", ["la-doctor", "trmv-typecheck", "trmv"]),
        ("retrmvx", []),
        ("xarc42y", []),
        ("pr_plan and trmv_x", []),
        ("my-trmv", ["trmv"]),
        ("cat living-architecture.yaml", ["living-architecture.yaml", "living-architecture"]),
        ("# ALLOW(import-not-top): x", ["ALLOW("]),
        ("run /la:pr then /trmv:init", ["/la:", "/trmv:", "trmv"]),
        ("[LikeC4](https://likec4.dev) and **openspec**", ["LikeC4", "OpenSpec"]),
        ("Reset Point 2", ["reset point"]),
        ("reset  point", []),
        ("trmv, trmv and TRMV", ["trmv"]),
        ("see .basedpyright/baseline.json", [".basedpyright/baseline.json"]),
        ("nothing here", []),
    ],
)
def test_find_tokens(line: str, hits: list[str]) -> None:
    """Whole tokens, case-insensitively, in contract spelling, by start then longer first, each once."""
    assert find_tokens(line, TOKENS) == hits


def test_leak_tokens_hold_every_core_waivable_command_and_registry_token(tmp_path: Path) -> None:
    tokens = leak_tokens(repo_root=_repo(tmp_path, {}), allow=[])
    expected = {*CORE, *WAIVABLE, *REGISTRY, *_commands("la"), *_commands("trmv")}
    assert expected - set(tokens) == set()


def test_allow_drops_only_the_listed_waivable_tokens(tmp_path: Path) -> None:
    tokens = leak_tokens(repo_root=_repo(tmp_path, {}), allow=["arc42", "pr-plan"])
    assert ("arc42" in tokens, "pr-plan" in tokens, "LikeC4" in tokens) == (False, False, True)


@pytest.mark.parametrize("token", CORE)
def test_core_tokens_survive_allow(tmp_path: Path, token: str) -> None:
    assert token in leak_tokens(repo_root=_repo(tmp_path, {}), allow=[token])


def test_openspec_dropped_when_the_repo_tracks_openspec(tmp_path: Path) -> None:
    tokens = leak_tokens(repo_root=_repo(tmp_path, {"openspec/specs/a/spec.md": "# a\n"}), allow=[])
    assert "OpenSpec" not in tokens


def test_openspec_kept_for_an_untracked_openspec_dir(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"README.md": "x\n"})
    (repo / "openspec" / "specs").mkdir(parents=True)
    (repo / "openspec" / "specs" / "spec.md").write_text("# a\n", encoding="utf-8")
    assert "OpenSpec" in leak_tokens(repo_root=repo, allow=[])
