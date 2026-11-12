"""What a branch changed against its base: base-ref resolution and the NUL-delimited git change listing."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
from pathlib import Path

from living_architecture.config import ConfigError
from living_architecture.contract import base_fetch_timeout, message

__all__ = ["changed_paths", "git_paths", "pr_base", "resolve_base_ref"]

# Neither git nor ssh may prompt during the fetch: no terminal prompt and no askpass helper.
_NO_PROMPT = {"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "SSH_ASKPASS": "", "SSH_ASKPASS_REQUIRE": "never"}


def _git(args: list[str], *, cwd: Path) -> bytes:
    try:
        proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)
    except OSError as exc:
        raise ConfigError(message("changes.git-failed", args=" ".join(args))) from exc
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
    try:
        proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise ConfigError(message("changes.pr-base-unresolved", pr=pr)) from exc
    base = proc.stdout.strip()
    if proc.returncode != 0 or not base:
        raise ConfigError(message("changes.pr-base-unresolved", pr=pr))
    return base


def _bounded_fetch(base: str, repo_root: Path, timeout: float) -> None:
    """`git fetch origin <base>` in its own process group, the whole group killed after `timeout` seconds."""
    env = {**os.environ, **_NO_PROMPT}
    try:
        proc = subprocess.Popen(["git", "fetch", "origin", base, "--quiet"], cwd=repo_root, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, start_new_session=True)
    except OSError:
        return
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        if hasattr(os, "killpg"):
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
        proc.wait()


def resolve_base_ref(*, base: str, repo_root: Path, fetch_timeout: float | None = None) -> str:
    """`origin/<base>` after a best-effort, bounded, non-prompting fetch; ConfigError when it does not resolve."""
    _bounded_fetch(base, repo_root, base_fetch_timeout() if fetch_timeout is None else fetch_timeout)
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
