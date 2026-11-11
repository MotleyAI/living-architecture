"""What a branch changed against its base: base-ref resolution and the NUL-delimited git change listing."""

from __future__ import annotations

import subprocess
from pathlib import Path

from living_architecture.config import ConfigError
from living_architecture.contract import message

__all__ = ["changed_paths", "git_paths", "pr_base", "resolve_base_ref"]


def _git(args: list[str], *, cwd: Path) -> bytes:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise ConfigError(detail or message("changes.git-failed", args=" ".join(args)))
    return proc.stdout


def git_paths(args: list[str], *, repo_root: Path) -> list[str]:
    """The NUL-delimited paths a git listing prints; undecodable bytes kept as surrogate escapes."""
    return [p.decode("utf-8", "surrogateescape") for p in _git(args, cwd=repo_root).split(b"\0") if p]


def pr_base(*, pr: str | None, repo: str | None, repo_root: Path) -> str:
    """The base branch of PR `pr` through `gh`."""
    cmd = ["gh", "pr", "view", str(pr), "--json", "baseRefName", "--jq", ".baseRefName"]
    if repo:
        cmd += ["--repo", repo]
    proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=False)
    base = proc.stdout.strip()
    if proc.returncode != 0 or not base:
        raise ConfigError(message("changes.pr-base-unresolved", pr=pr))
    return base


def resolve_base_ref(*, base: str, repo_root: Path) -> str:
    """`origin/<base>` after a best-effort fetch; ConfigError when it does not resolve."""
    subprocess.run(["git", "fetch", "origin", base, "--quiet"], cwd=repo_root, capture_output=True, check=False)
    ref = f"origin/{base}"
    _git(["rev-parse", "--verify", "--quiet", ref], cwd=repo_root)
    return ref


def changed_paths(*, base_ref: str, repo_root: Path, deletions: bool, untracked: bool) -> list[str]:
    """Paths changed since the merge base with `base_ref`, committed or not, in code-point order; renames split."""
    diff = ["diff", "-z", "--name-only", "--no-renames"] + ([] if deletions else ["--diff-filter=ACMR"])
    out: set[str] = set()
    for target in (f"{base_ref}...HEAD", "HEAD"):
        out.update(git_paths([*diff, target], repo_root=repo_root))
    if untracked:
        out.update(git_paths(["ls-files", "-z", "--others", "--exclude-standard"], repo_root=repo_root))
    return sorted(out)
