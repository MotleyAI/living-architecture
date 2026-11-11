"""The change set: base-ref resolution and the NUL-delimited git change listing."""

import subprocess
from pathlib import Path

import pytest

from living_architecture import changes
from living_architecture.config import ConfigError
from living_architecture.contract import message


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _write(repo: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _write(tmp_path, {"kept.py": "", "modified.py": "", "deleted.py": "", "old.py": "", "staged.py": "",
                      "unstaged.py": "", "gone.py": ""})
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(tmp_path, "checkout", "-q", "-b", "feat")
    _write(tmp_path, {"modified.py": "X = 1\n", "added.py": "", "notes.txt": "x\n"})
    _git(tmp_path, "rm", "-q", "deleted.py")
    _git(tmp_path, "mv", "old.py", "new.py")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "work")
    _write(tmp_path, {"staged.py": "X = 1\n", "unstaged.py": "X = 1\n", "untracked.py": "", "ignored.py": "",
                      ".gitignore": "ignored.py\n"})
    _git(tmp_path, "add", "staged.py")
    (tmp_path / "gone.py").unlink()
    return tmp_path


def test_resolve_base_ref_is_the_origin_branch(repo):
    assert changes.resolve_base_ref(base="main", repo_root=repo) == "origin/main"


def test_resolve_base_ref_missing(repo):
    with pytest.raises(ConfigError) as exc:
        changes.resolve_base_ref(base="nope", repo_root=repo)
    assert str(exc.value) == "git rev-parse --verify --quiet origin/nope failed"


def test_listing_without_deletions_or_untracked(repo):
    listed = changes.changed_paths(base_ref="origin/main", repo_root=repo, deletions=False, untracked=False)
    assert listed == ["added.py", "modified.py", "new.py", "notes.txt", "staged.py", "unstaged.py"]


def test_listing_with_deletions_and_untracked(repo):
    listed = changes.changed_paths(base_ref="origin/main", repo_root=repo, deletions=True, untracked=True)
    assert listed == [".gitignore", "added.py", "deleted.py", "gone.py", "modified.py", "new.py", "notes.txt",
                      "old.py", "staged.py", "unstaged.py", "untracked.py"]


def test_listing_keeps_real_names_in_code_point_order(repo):
    _write(repo, {"b c.py": "", "données.py": "", "Zed.py": "", "-dash.py": ""})
    listed = changes.changed_paths(base_ref="origin/main", repo_root=repo, deletions=False, untracked=True)
    named = [p for p in listed if p in {"b c.py", "données.py", "Zed.py", "-dash.py"}]
    assert named == ["-dash.py", "Zed.py", "b c.py", "données.py"]


def test_git_texts_moved_with_identical_wording():
    assert message("changes.git-failed", args="diff HEAD") == "git diff HEAD failed"
    assert message("changes.pr-base-unresolved", pr=7) == "could not resolve the base branch of PR 7"
