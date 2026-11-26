"""The stealth merge-base baseline: its cache key and the temporary merge-base checkout."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from trmv.lang import merge_base_checkout
from trmv.typecheck import cache_key

KEY = {"commit": "a" * 40, "language": "python", "command": "basedpyright", "version": "1.2.3",
       "fingerprints": {"pyproject.toml": b"[project]\n", "uv.lock": b"lock\n"}}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    (root / "m.py").write_text("X = 1\n", encoding="utf-8")
    (root / ".gitignore").write_text(".venv/\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")
    (root / ".venv" / "bin").mkdir(parents=True)
    return root


def test_cache_key_is_deterministic() -> None:
    assert cache_key(**KEY) == cache_key(**KEY)


@pytest.mark.parametrize(("field", "value"), [
    ("commit", "b" * 40), ("language", "typescript"), ("command", "basedpyright --level error"), ("version", "1.2.4"),
    ("fingerprints", {"pyproject.toml": b"[project]\n# edited\n", "uv.lock": b"lock\n"}),
    ("fingerprints", {"pyproject.toml": b"[project]\n"}),
])
def test_cache_key_changes_with_each_input(field: str, value: object) -> None:
    assert cache_key(**{**KEY, field: value}) != cache_key(**KEY)


def test_cache_key_ignores_fingerprint_order() -> None:
    reordered = dict(reversed(list(KEY["fingerprints"].items())))
    assert cache_key(**{**KEY, "fingerprints": reordered}) == cache_key(**KEY)


def test_checkout_links_environment_dirs_outside_the_repo(repo: Path) -> None:
    commit = _git(repo, "rev-parse", "HEAD").strip()
    with merge_base_checkout(repo, commit, [".venv", "node_modules"]) as checkout:
        assert (checkout / "m.py").read_text(encoding="utf-8") == "X = 1\n"
        assert (checkout / ".venv").resolve() == (repo / ".venv").resolve()
        assert not (checkout / "node_modules").exists()
        assert not checkout.resolve().is_relative_to(repo.resolve())
        assert str(checkout) in _git(repo, "worktree", "list", "--porcelain")


def test_checkout_is_removed_and_pruned(repo: Path) -> None:
    with merge_base_checkout(repo, _git(repo, "rev-parse", "HEAD").strip(), [".venv"]) as checkout:
        pass
    assert not checkout.exists()
    assert str(checkout) not in _git(repo, "worktree", "list", "--porcelain")


def _fail_inside(repo: Path, commit: str, seen: list[Path]) -> None:
    with merge_base_checkout(repo, commit, []) as checkout:
        seen.append(checkout)
        raise RuntimeError("boom")


def test_checkout_is_removed_and_pruned_on_an_exception(repo: Path) -> None:
    seen: list[Path] = []
    commit = _git(repo, "rev-parse", "HEAD").strip()
    with pytest.raises(RuntimeError, match="boom"):
        _fail_inside(repo, commit, seen)
    assert not seen[0].exists()
    assert str(seen[0]) not in _git(repo, "worktree", "list", "--porcelain")
