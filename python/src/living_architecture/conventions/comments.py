"""`la-count-comments`: count comment and doc lines, per file or net added versus a git ref, every language."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from living_architecture.config import find_repo_root
from living_architecture.contract import manifest, message
from living_architecture.conventions.facts import FactsError, collect, language_of

_PROG = "la-count-comments"


def _usage() -> int:
    print(manifest()[_PROG]["usage"], file=sys.stderr)
    return 2


def _known(paths: list[str]) -> list[str]:
    for path in paths:
        if language_of(path) is None:
            print(message("count-comments.unknown-extension", path=path), file=sys.stderr)
    return [p for p in paths if language_of(p) is not None]


def _counts(entry: dict[str, Any] | None) -> tuple[int, int]:
    """(comment, doc) lines; zeros for a missing or unreadable file."""
    if entry is None or "comment_lines" not in entry:
        return 0, 0
    return entry["comment_lines"], entry["doc_lines"]


def _base_tree(ref: str, paths: list[str], *, cwd: Path, tree: Path) -> list[str]:
    """Write each path's bytes at `ref` under `tree`; the paths that exist there."""
    present = []
    for path in paths:
        rel = PurePosixPath(path)
        if rel.is_absolute() or ".." in rel.parts:
            continue
        proc = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=cwd, capture_output=True, check=False)
        if proc.returncode == 0:
            (tree / rel).parent.mkdir(parents=True, exist_ok=True)
            (tree / rel).write_bytes(proc.stdout)
            present.append(path)
    return present


def _print_range(ref: str, paths: list[str], *, cwd: Path, repo_root: Path) -> None:
    head = collect(paths, cwd=cwd, repo_root=repo_root)
    with tempfile.TemporaryDirectory(prefix="la-count-comments-") as tmp:
        tree = Path(tmp)
        base = collect(_base_tree(ref, paths, cwd=cwd, tree=tree), cwd=tree, repo_root=repo_root)
    tc = td = 0
    for p in paths:
        (hc, hd), (bc, bd) = _counts(head.get(p)), _counts(base.get(p))
        dc, dd = hc - bc, hd - bd
        print(message("count-comments.file", total=f"{dc + dd:+5d}", comment=f"{dc:+4d}", doc=f"{dd:+4d}", path=p))
        tc += dc
        td += dd
    print(message("count-comments.net-added", total=tc + td, comment=tc, doc=td))


def _print_files(paths: list[str], *, cwd: Path, repo_root: Path) -> None:
    facts = collect(paths, cwd=cwd, repo_root=repo_root)
    tc = td = 0
    for p in paths:
        c, d = _counts(facts.get(p))
        print(message("count-comments.file", total=f"{c + d:5d}", comment=f"{c:4d}", doc=f"{d:4d}", path=p))
        tc += c
        td += d
    print(message("count-comments.total", total=tc + td, comment=tc, doc=td))


def count_comments(args: list[str]) -> int:
    """Handler for raw argv: `FILE...` or `--range REF PATH...`."""
    ranged = args[:1] == ["--range"]
    if (ranged and len(args) < 3) or not args:
        return _usage()
    cwd = Path.cwd()
    repo_root = find_repo_root(cwd)
    try:
        if ranged:
            _print_range(args[1], _known(args[2:]), cwd=cwd, repo_root=repo_root)
        else:
            _print_files(_known(args), cwd=cwd, repo_root=repo_root)
    except FactsError as exc:
        if str(exc):
            print(message("twin.error", prog=_PROG, error=str(exc)), file=sys.stderr)
        return 2
    return 0
