"""`la-count-comments`: count comment + docstring lines in Python files.

  la-count-comments FILE...                  per-file + total counts
  la-count-comments --range REF PATH...      net added vs a git ref (working tree)
"""

from __future__ import annotations

import ast
import io
import subprocess
import sys
import tokenize

_DOC_OWNERS = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def counts(src: str | None) -> tuple[int, int]:
    """(comment lines, docstring lines); zeros for a missing file."""
    if src is None:
        return 0, 0
    try:
        comment = sum(1 for t in tokenize.generate_tokens(io.StringIO(src).readline) if t.type == tokenize.COMMENT)
    except (tokenize.TokenError, SyntaxError):
        comment = 0
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return comment, 0
    doc = 0
    for node in ast.walk(tree):
        if isinstance(node, _DOC_OWNERS) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                doc += (first.end_lineno or first.lineno) - first.lineno + 1
    return comment, doc


def _git_show(ref: str, path: str) -> str | None:
    r = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True, check=False)
    return r.stdout if r.returncode == 0 else None


def _read(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["--range"]:
        if len(args) < 3:
            print(__doc__, file=sys.stderr)
            return 2
        ref, paths = args[1], args[2:]
        tc = td = 0
        for p in paths:
            base, head = counts(_git_show(ref, p)), counts(_read(p))
            dc, dd = head[0] - base[0], head[1] - base[1]
            print(f"{dc + dd:+5d}  comment={dc:+4d} doc={dd:+4d}  {p}")
            tc += dc
            td += dd
        print(f"{'=' * 50}\nNET ADDED total={tc + td} (comment {tc}, docstring {td})")
        return 0
    if not args:
        print(__doc__, file=sys.stderr)
        return 2
    tc = td = 0
    for p in args:
        c, d = counts(_read(p))
        print(f"{c + d:5d}  comment={c:4d} doc={d:4d}  {p}")
        tc += c
        td += d
    print(f"{'=' * 50}\nTOTAL={tc + td} (comment {tc}, docstring {td})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
