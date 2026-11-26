"""`la-leak-check`: the tokens that show la or trmv was used, in a stealth branch or in a text."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from living_architecture.config import RawConfig, load_raw, resolve_raw, tracks_openspec
from living_architecture.contract import leak_token_groups, manifest, message, stealth_registry
from trmv import changes
from trmv.config import ConfigError, present_files
from trmv.contract import manifest as trmv_manifest
from trmv.contract import stealth_registry as trmv_registry

_ASCII_LOWER = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def _word(char: str) -> bool:
    return char.isalnum() or char == "_"


def _first_match(text: str, token: str) -> int | None:
    """Where `token` (lowercase) first occurs in `text` (ASCII-lowercased) with no word character touching it."""
    start = text.find(token)
    while start >= 0:
        end = start + len(token)
        before = start > 0 and _word(token[0]) and _word(text[start - 1])
        after = end < len(text) and _word(token[-1]) and _word(text[end])
        if not before and not after:
            return start
        start = text.find(token, start + 1)
    return None


def find_tokens(text: str, tokens: list[str]) -> list[str]:
    """The tokens `text` holds, case-insensitively, each once, by first position and then longer first."""
    lowered = text.translate(_ASCII_LOWER)
    found: list[tuple[int, int, str]] = []
    for token in dict.fromkeys(tokens):
        start = _first_match(lowered, token.translate(_ASCII_LOWER))
        if start is not None:
            found.append((start, -len(token), token))
    return [token for _, _, token in sorted(found, key=lambda hit: (hit[0], hit[1]))]


def leak_tokens(*, repo_root: Path, allow: list[str]) -> list[str]:
    """The core tokens, every command name and registry path, and the waivable tokens not in `allow` (OpenSpec only
    when the repo tracks nothing under openspec/)."""
    core, waivable = leak_token_groups()
    commands = [*manifest(), *trmv_manifest()]
    registry = [*stealth_registry()[0], *trmv_registry()]
    dropped = {*allow, *(["OpenSpec"] if tracks_openspec(repo_root) else [])}
    return list(dict.fromkeys([*core, *commands, *registry, *(t for t in waivable if t not in dropped)]))


def _git(root: Path, *args: str) -> bytes:
    try:
        proc = subprocess.run(["git", *args], cwd=root, capture_output=True, check=False)
    except OSError as exc:
        raise ConfigError(message("changes.git-failed", args=" ".join(args))) from exc
    if proc.returncode != 0:
        raise ConfigError(message("changes.git-failed", args=" ".join(args)))
    return proc.stdout


def _text(data: bytes) -> str:
    return data.decode("utf-8", "replace")


def _branch(root: Path) -> str | None:
    proc = subprocess.run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], cwd=root, capture_output=True,
                          check=False)
    name = _text(proc.stdout).strip()
    return name if proc.returncode == 0 and name else None


def _commits(root: Path, merge_base: str) -> list[tuple[str, str]]:
    """Each commit since `merge_base`, oldest first, with its full message."""
    out = _git(root, "log", "--reverse", "-z", "--format=%H%n%B", f"{merge_base}..HEAD")
    records = [_text(r) for r in out.split(b"\0") if r]
    return [(r.split("\n", 1)[0], r.split("\n", 1)[1] if "\n" in r else "") for r in records]


def _entries(root: Path, merge_base: str) -> list[tuple[str, str, str]]:
    """Each path changed between `merge_base` and HEAD but deleted: its status letter, old path and new path."""
    fields = [_text(f) for f in _git(root, "diff", "-z", "--name-status", "-M", merge_base, "HEAD", "--").split(b"\0")]
    out: list[tuple[str, str, str]] = []
    i = 0
    while i < len(fields) and fields[i]:
        status = fields[i][0]
        if status in "RC":
            out.append((status, fields[i + 1], fields[i + 2]))
            i += 3
        else:
            out.append((status, fields[i + 1], fields[i + 1]))
            i += 2
    return [entry for entry in out if entry[0] != "D"]


def _added_lines(root: Path, merge_base: str, old: str, new: str) -> list[tuple[int, str]]:
    """The lines the diff of one path adds, with their line numbers in the new file."""
    patch = _git(root, "diff", "-U0", "--no-color", "--no-ext-diff", "-M", merge_base, "HEAD", "--", old, new)
    out: list[tuple[int, str]] = []
    number: int | None = None
    for raw in _text(patch).split("\n"):
        if raw.startswith("@@ "):
            new_range = raw.split(" ")[2]
            number = int(new_range[1:].split(",")[0])
        elif number is not None and raw.startswith("+"):
            out.append((number, raw[1:]))
            number += 1
    return out


def scan_branch(root: Path, base_ref: str, tokens: list[str]) -> list[str]:
    """The hits of the branch name, the commit messages and the added paths and lines since the merge base."""
    merge_base = changes.merge_base(base_ref=base_ref, repo_root=root)
    hits: list[str] = []
    branch = _branch(root)
    if branch is not None:
        hits += [message("leaks.branch", token=t) for t in find_tokens(branch, tokens)]
    for commit, body in _commits(root, merge_base):
        hits += [message("leaks.commit", commit=commit[:7], token=t) for t in find_tokens(body, tokens)]
    for status, old, new in sorted(_entries(root, merge_base), key=lambda entry: entry[2]):
        if status in "ARC":
            hits += [message("leaks.path", path=new, token=t) for t in find_tokens(new, tokens)]
        for number, line in _added_lines(root, merge_base, old, new):
            hits += [message("leaks.line", path=new, line=number, token=t) for t in find_tokens(line, tokens)]
    return hits


def scan_text(text: str, tokens: list[str]) -> list[str]:
    """The hits of each line of `text`."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [message("leaks.stdin", line=n, token=t) for n, line in enumerate(lines, 1) for t in find_tokens(line, tokens)]


def _load_raw(root: Path) -> RawConfig | None:
    """The raw config; None on a config error when no stealth config file is present."""
    try:
        return load_raw(root)
    except ConfigError:
        if any(f.stealth for f in present_files(root)):
            raise
        return None


def run(*, base: str | None, root: Path) -> int:
    """`la-leak-check`: print each hit; exit 1 with hits, 0 without or outside stealth mode, 2 on an error."""
    try:
        raw = _load_raw(root)
        if raw is None or raw.source is None or not raw.source.stealth:
            print(message("leaks.not-stealth"), file=sys.stderr)
            return 0
        config = resolve_raw(root, raw)
        tokens = leak_tokens(repo_root=root, allow=config.leaks.allow)
        if base is None:
            hits = scan_text(sys.stdin.buffer.read().decode("utf-8", "replace"), tokens)
        else:
            hits = scan_branch(root, changes.resolve_base_ref(base=base, repo_root=root), tokens)
    except ConfigError as exc:
        print(message("leaks.error", error=str(exc)), file=sys.stderr)
        return 2
    for hit in hits:
        print(hit)
    return 1 if hits else 0
