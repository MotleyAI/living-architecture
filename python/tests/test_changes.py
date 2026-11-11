"""The change set: base-ref resolution and the NUL-delimited git change listing."""

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from living_architecture import changes
from living_architecture.config import ConfigError
from living_architecture.contract import base_fetch_timeout, message


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


@pytest.fixture
def no_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))


def test_resolve_base_ref_without_git(repo, no_tools):
    with pytest.raises(ConfigError) as exc:
        changes.resolve_base_ref(base="main", repo_root=repo)
    assert str(exc.value) == "git rev-parse --verify --quiet origin/main failed"


def test_pr_base_without_gh(repo, no_tools):
    with pytest.raises(ConfigError) as exc:
        changes.pr_base(pr="7", repo=None, repo_root=repo)
    assert str(exc.value) == "could not resolve the base branch of PR 7"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.mark.skipif(not hasattr(os, "killpg"), reason="needs process groups")
def test_a_stalled_fetch_is_bounded_and_never_prompts(repo, tmp_path, monkeypatch):
    git, sleep = shutil.which("git"), shutil.which("sleep")
    assert git is not None
    assert sleep is not None
    fake = tmp_path / "slow-git"
    fake.mkdir()
    (fake / "git").write_text(
        f'#!/bin/sh\nif [ "$1" = fetch ]; then echo "$GIT_TERMINAL_PROMPT|${{GIT_ASKPASS-unset}}|${{SSH_ASKPASS-unset}}|'
        f'$SSH_ASKPASS_REQUIRE" > "{fake}/prompt"\n'
        f'  "{sleep}" 30 & echo $! > "{fake}/helper"; wait; fi\nexec "{git}" "$@"\n'
    )
    (fake / "git").chmod(0o755)
    monkeypatch.setenv("PATH", str(fake))
    start = time.monotonic()
    assert changes.resolve_base_ref(base="main", repo_root=repo, fetch_timeout=0.5) == "origin/main"
    assert time.monotonic() - start < 10
    assert (fake / "prompt").read_text() == "0|||never\n"
    helper = int((fake / "helper").read_text())
    deadline = time.monotonic() + 5
    while _alive(helper) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _alive(helper)


def test_the_fetch_timeout_comes_from_the_shared_contract():
    assert base_fetch_timeout() == 30


def test_git_texts_moved_with_identical_wording():
    assert message("changes.git-failed", args="diff HEAD") == "git diff HEAD failed"
    assert message("changes.pr-base-unresolved", pr=7) == "could not resolve the base branch of PR 7"
