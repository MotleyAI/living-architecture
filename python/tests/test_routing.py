"""dr-* directory expansion: excluded directory names count from the repo root down."""

import subprocess
from pathlib import Path

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
