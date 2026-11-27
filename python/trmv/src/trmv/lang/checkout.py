"""A checker environment for another revision: a temporary linked worktree with the environment directories linked in."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


class CheckoutError(Exception):
    """The temporary worktree could not be created."""


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)


@contextmanager
def merge_base_checkout(repo: Path, commit: str, environment_dirs: list[str]) -> Generator[Path]:
    """`commit` checked out in a temporary linked worktree outside `repo`, with each of `environment_dirs` that exists
    in `repo` linked in; removed and pruned on every exit path."""
    parent = Path(tempfile.mkdtemp(prefix="trmv-merge-base-")).resolve()
    checkout = parent / "checkout"
    try:
        added = _git(repo, "worktree", "add", "--detach", "--quiet", str(checkout), commit)
        if added.returncode != 0:
            raise CheckoutError(added.stderr.decode("utf-8", "replace").strip())
        for name in environment_dirs:
            source = repo / name
            if source.is_dir() and not (checkout / name).exists():
                os.symlink(source.resolve(), checkout / name, target_is_directory=True)
        yield checkout
    finally:
        for name in environment_dirs:
            if (checkout / name).is_symlink():
                (checkout / name).unlink()
        _git(repo, "worktree", "remove", "--force", str(checkout))
        shutil.rmtree(parent, ignore_errors=True)
        _git(repo, "worktree", "prune")
