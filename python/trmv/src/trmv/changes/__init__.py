"""What a branch changed against its base: base-ref resolution and the NUL-delimited git change listing."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
from pathlib import Path

from trmv.config import ConfigError
from trmv.contract import base_fetch_timeout, message

__all__ = [
    "base_paths",
    "changed_paths",
    "commit_id",
    "default_base_ref",
    "file_at",
    "git_paths",
    "is_commit",
    "merge_base",
    "resolve_base_ref",
    "tracked_at_head",
]

# Neither git nor ssh may prompt during the fetch: no terminal prompt and no askpass helper.
_NO_PROMPT = {"GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "", "SSH_ASKPASS": "", "SSH_ASKPASS_REQUIRE": "never"}


def _failed(args: list[str]) -> str:
    return message("changes.git-failed", args=" ".join(args))


def _started(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)
    except OSError as exc:
        raise ConfigError(_failed(args)) from exc


def _git(args: list[str], *, cwd: Path) -> bytes:
    proc = _started(args, cwd=cwd)
    if proc.returncode != 0:
        raise ConfigError(proc.stderr.decode("utf-8", "replace").strip() or _failed(args))
    return proc.stdout


def git_paths(args: list[str], *, repo_root: Path) -> list[str]:
    """The NUL-delimited paths a git listing prints; undecodable bytes kept as surrogate escapes."""
    return [p.decode("utf-8", "surrogateescape") for p in _git(args, cwd=repo_root).split(b"\0") if p]


def _bounded_fetch(remote: str, branch: str, repo_root: Path, timeout: float) -> None:
    """`git fetch <remote> <branch>` in its own process group, the whole group killed after `timeout` seconds."""
    env = {**os.environ, **_NO_PROMPT}
    try:
        proc = subprocess.Popen(["git", "fetch", remote, branch, "--quiet"], cwd=repo_root, stdin=subprocess.DEVNULL,
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


def _remotes(repo_root: Path) -> list[str]:
    """The configured git remotes; none when git cannot list them."""
    try:
        proc = subprocess.run(["git", "remote"], cwd=repo_root, capture_output=True, check=False)
    except OSError:
        return []
    return proc.stdout.decode("utf-8", "surrogateescape").split() if proc.returncode == 0 else []


def resolve_base_ref(*, base: str, repo_root: Path, fetch_timeout: float | None = None) -> str:
    """The base ref `base` names, after a best-effort, bounded, non-prompting fetch: `refs/remotes/<remote>/<rest>` when
    `base` is `<remote>/<rest>` of a configured remote, else `origin/<base>`; ConfigError when it does not resolve."""
    timeout = base_fetch_timeout() if fetch_timeout is None else fetch_timeout
    remote, _, rest = base.partition("/")
    if rest and remote in _remotes(repo_root):
        _bounded_fetch(remote, rest, repo_root, timeout)
        ref = f"refs/remotes/{remote}/{rest}"
    else:
        _bounded_fetch("origin", base, repo_root, timeout)
        ref = f"origin/{base}"
    _git(["rev-parse", "--verify", "--quiet", ref], cwd=repo_root)
    return ref


def default_base_ref(repo_root: Path) -> str | None:
    """The ref `refs/remotes/origin/HEAD` points to, None without it."""
    proc = _started(["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"], cwd=repo_root)
    ref = proc.stdout.decode().strip()
    return ref if proc.returncode == 0 and ref else None


def changed_paths(*, base_ref: str, repo_root: Path, deletions: bool, untracked: bool) -> list[str]:
    """Paths changed since the merge base with `base_ref`, committed or not, in code-point order; renames split."""
    diff = ["diff", "-z", "--name-only", "--no-renames"] + ([] if deletions else ["--diff-filter=ACMR"])
    out: set[str] = set()
    for target in (f"{base_ref}...HEAD", "HEAD"):
        out.update(git_paths([*diff, target, "--"], repo_root=repo_root))
    if untracked:
        out.update(git_paths(["ls-files", "-z", "--others", "--exclude-standard"], repo_root=repo_root))
    return sorted(out)


def merge_base(*, base_ref: str, repo_root: Path) -> str:
    """The merge base of `base_ref` and HEAD."""
    return _git(["merge-base", base_ref, "HEAD"], cwd=repo_root).decode().strip()


def commit_id(*, ref: str, repo_root: Path) -> str | None:
    """The id of the commit `ref` names, None when it names none; ConfigError when git fails."""
    proc = _started(["rev-parse", "--verify", "--quiet", "--end-of-options", f"{ref}^{{commit}}"], cwd=repo_root)
    if proc.returncode == 0:
        return proc.stdout.decode().strip()
    detail = proc.stderr.decode("utf-8", "replace").strip()
    if detail:
        raise ConfigError(detail)
    return None


def is_commit(*, ref: str, repo_root: Path) -> bool:
    """Whether `ref` names a commit."""
    return commit_id(ref=ref, repo_root=repo_root) is not None


def file_at(*, ref: str, path: str, repo_root: Path) -> bytes | None:
    """The bytes of repo-relative `path` at `ref`, None when it is not there."""
    proc = subprocess.run(["git", "cat-file", "blob", f"{ref}:{path}"], cwd=repo_root, capture_output=True, check=False)
    return proc.stdout if proc.returncode == 0 else None


def tracked_at_head(*, path: str, repo_root: Path) -> bool:
    """Whether HEAD tracks repo-relative `path`."""
    return file_at(ref="HEAD", path=path, repo_root=repo_root) is not None


def base_paths(*, ref: str, repo_root: Path) -> dict[str, str]:
    """Each path renamed since `ref` (tracked files of the working tree), mapped to its path at `ref`."""
    fields = git_paths(["diff", "-z", "--name-status", "-M", ref, "--"], repo_root=repo_root)
    out: dict[str, str] = {}
    i = 0
    while i < len(fields):
        status = fields[i]
        if status.startswith("R"):
            out[fields[i + 2]] = fields[i + 1]
            i += 3
        else:
            i += 2
    return out
