"""dr-* directory expansion: excluded directory names count from the repo root down."""

import subprocess
from pathlib import Path

import pytest

from living_architecture.refactor import routing
from living_architecture.refactor.routing import split


def _repo_under_node_modules(tmp_path: Path) -> Path:
    repo = tmp_path / "node_modules" / "repo"
    for rel, text in {"tsconfig.json": "{}", "src/a.ts": "export {};\n", "node_modules/dep/b.ts": "export {};\n"}.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    return repo


def test_an_excluded_ancestor_outside_the_repo_does_not_count(tmp_path: Path) -> None:
    repo = _repo_under_node_modules(tmp_path)
    assert split("dr-compliance", [str(repo / "src")], repo) == {"typescript": [str(repo / "src" / "a.ts")]}


def test_a_requested_directory_inside_an_excluded_one_expands_to_nothing(tmp_path: Path) -> None:
    repo = _repo_under_node_modules(tmp_path)
    assert split("dr-compliance", [str(repo / "node_modules" / "dep")], repo) == {}


def test_a_directory_inside_an_excluded_one_is_not_walked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo_under_node_modules(tmp_path)
    walked: list[str] = []
    monkeypatch.setattr(routing.os, "walk", lambda top: walked.append(str(top)) or iter(()))
    split("dr-compliance", [str(repo / "node_modules" / "dep")], repo)
    assert routing.source_language(str(repo / "node_modules" / "dep"), str(repo)) is None
    assert walked == []


def test_an_unreadable_directory_is_skipped(tmp_path: Path) -> None:
    repo = _repo_under_node_modules(tmp_path)
    locked = repo / "src" / "locked"
    locked.mkdir()
    locked.chmod(0o000)
    try:
        assert split("dr-compliance", [str(repo / "src")], repo) == {"typescript": [str(repo / "src" / "a.ts")]}
    finally:
        locked.chmod(0o755)
