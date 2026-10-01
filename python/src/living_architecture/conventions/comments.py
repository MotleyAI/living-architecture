"""`la-count-comments`: count comment and docstring lines, per file or net added versus a git ref."""

from __future__ import annotations

import subprocess
import sys

from living_architecture.contract import manifest, message
from living_architecture.lang import comment_doc_counts


def _git_show(ref: str, path: str) -> str | None:
    r = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True, check=False)
    return r.stdout if r.returncode == 0 else None


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def _usage() -> int:
    print(manifest()["la-count-comments"]["usage"], file=sys.stderr)
    return 2


def count_comments(args: list[str]) -> int:
    """Handler for raw argv: `FILE...` or `--range REF PATH...`."""
    if args[:1] == ["--range"]:
        if len(args) < 3:
            return _usage()
        ref, paths = args[1], args[2:]
        tc = td = 0
        for p in paths:
            base, head = comment_doc_counts(_git_show(ref, p)), comment_doc_counts(_read(p))
            dc, dd = head[0] - base[0], head[1] - base[1]
            print(message("count-comments.file", total=f"{dc + dd:+5d}", comment=f"{dc:+4d}", doc=f"{dd:+4d}", path=p))
            tc += dc
            td += dd
        print(message("count-comments.net-added", total=tc + td, comment=tc, doc=td))
        return 0
    if not args:
        return _usage()
    tc = td = 0
    for p in args:
        c, d = comment_doc_counts(_read(p))
        print(message("count-comments.file", total=f"{c + d:5d}", comment=f"{c:4d}", doc=f"{d:4d}", path=p))
        tc += c
        td += d
    print(message("count-comments.total", total=tc + td, comment=tc, doc=td))
    return 0
