"""`la-check-conventions`: deterministic convention gate over a PR's changed .py files.

Rules (whole file, for every .py file the PR changed):

  [import-not-top]       no imports inside functions, none after module-level code
                         (import-only ``if``/``try`` wrappers count as prologue).
  [text-ratio]           docstring + comment-only lines <= the cap, aggregated
                         separately over test and source files. No per-line waiver.
  [composite-assert]     (tests) ``assert a and b`` — split it.
  [raises-single-throw]  (tests) a ``pytest.raises`` block making more than one call.

Waiver: a trailing ``# ALLOW(<rule>): <reason>`` on the flagged line (not for
text-ratio). Exit 0 clean, 1 violations, 2 usage/git error.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import io
import re
import subprocess
import sys
import tokenize
from collections.abc import Callable, Iterator
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from living_architecture.config import ConfigError, find_repo_root, load_config

_WAIVER_RE = re.compile(r"#\s*ALLOW\((?P<rule>[a-z-]+)\)\s*:\s*\S")

IMPORT_NOT_TOP = "import-not-top"
TEXT_RATIO = "text-ratio"
COMPOSITE_ASSERT = "composite-assert"
RAISES_SINGLE_THROW = "raises-single-throw"

_RAISES_CALLEES = ("raises", "assertRaises", "assertRaisesRegex", "assertRaisesRegexp")
_TOP_LEVEL_MSG = "module-level import after non-import code; move it to the top of the file"

GATE_RED_HINT = """
gate: RED —
  [import-not-top] hoist each flagged import to module top. Only a genuine
    circular import may be waived with '# ALLOW(import-not-top): <reason>' —
    confirm with the user before landing such a waiver.
  [text-ratio] trim comments/docstrings in the flagged file group until
    text-only lines fit under the cap (no per-line waiver)."""


class Violation(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    line: int
    rule: str
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: [{self.rule}] {self.message}"


class FileCounts(BaseModel):
    model_config = ConfigDict(frozen=True)

    rel: str
    text: int
    total: int


def _is_excluded(rel: str, *, patterns: list[str]) -> bool:
    rel_posix = Path(rel).as_posix()
    return any(fnmatch.fnmatch(rel_posix, pat) for pat in patterns)


def _is_docstring(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _contains_def(node: ast.stmt) -> bool:
    return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for n in ast.walk(node))


def _imports_in(node: ast.stmt) -> list[ast.stmt]:
    return [n for n in ast.walk(node) if isinstance(n, (ast.Import, ast.ImportFrom))]


def _is_import_wrapper(stmt: ast.stmt) -> bool:
    """A module-level ``if``/``try`` that only wraps imports (TYPE_CHECKING, optional deps)."""
    return isinstance(stmt, (ast.If, ast.Try)) and bool(_imports_in(stmt)) and not _contains_def(stmt)


def _imports_in_function(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.stmt]:
    """Imports directly inside ``fn``; nested defs are visited separately by the caller."""
    out: list[ast.stmt] = []
    stack: list[ast.stmt] = list(fn.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            out.append(node)
            continue
        stack.extend(child for child in ast.iter_child_nodes(node) if isinstance(child, ast.stmt))
    return out


def _check_imports_at_top(*, tree: ast.Module) -> Iterator[tuple[int, str]]:
    prologue_over = False
    for idx, stmt in enumerate(tree.body):
        if _is_docstring(stmt) and idx == 0:
            continue
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            if prologue_over:
                yield stmt.lineno, _TOP_LEVEL_MSG
            continue
        if _is_import_wrapper(stmt):
            if prologue_over:
                for imp in _imports_in(stmt):
                    yield imp.lineno, _TOP_LEVEL_MSG
            continue
        prologue_over = True
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for imp in _imports_in_function(node):
                yield imp.lineno, f"import inside function {node.name!r}; move it to the top of the file"


def _check_composite_asserts(*, tree: ast.Module) -> Iterator[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.BoolOp) and isinstance(node.test.op, ast.And):
            yield node.lineno, "composite `assert ... and ...`; split into separate assert statements"


def _is_raises_cm(expr: ast.expr) -> bool:
    if not isinstance(expr, ast.Call):
        return False
    func = expr.func
    if isinstance(func, ast.Attribute):
        return func.attr in _RAISES_CALLEES
    return isinstance(func, ast.Name) and func.id in _RAISES_CALLEES


def _check_raises_single_throw(*, tree: ast.Module) -> Iterator[tuple[int, str]]:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.With, ast.AsyncWith)):
            continue
        if not any(_is_raises_cm(item.context_expr) for item in node.items):
            continue
        calls = sum(isinstance(sub, ast.Call) for stmt in node.body for sub in ast.walk(stmt))
        if calls > 1:
            yield (
                node.lineno,
                (
                    f"`pytest.raises` block makes {calls} calls that can throw; move all but the call"
                    " under test outside the block"
                ),
            )


def _waived(*, source_lines: list[str], line: int, rule: str) -> bool:
    if not 1 <= line <= len(source_lines):
        return False
    m = _WAIVER_RE.search(source_lines[line - 1])
    return bool(m and m.group("rule") == rule)


def is_test_file(rel: str) -> bool:
    parts = Path(rel).parts
    name = parts[-1]
    return (
        any(p in ("tests", "test") for p in parts[:-1])
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
    )


def _text_line_numbers(*, source: str, tree: ast.Module) -> set[int]:
    """Docstring/standalone-string statement spans plus comment-only lines."""
    text: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.stmt) and _is_docstring(node):
            text.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT and not tok.line[: tok.start[1]].strip():
                text.add(tok.start[0])
    except tokenize.TokenError:
        pass
    return text


_TEST_RULES: tuple[tuple[str, Callable[..., Iterator[tuple[int, str]]]], ...] = (
    (COMPOSITE_ASSERT, _check_composite_asserts),
    (RAISES_SINGLE_THROW, _check_raises_single_throw),
)


def check_file(path: Path, *, rel: str) -> tuple[list[Violation], FileCounts | None]:
    """Violations plus text/total line counts (None when unreadable or unparsable)."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [Violation(path=rel, line=1, rule="unreadable", message=str(exc))], None
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [Violation(path=rel, line=exc.lineno or 1, rule="syntax-error", message=exc.msg or "syntax error")], None
    source_lines = source.splitlines()
    rules: list[tuple[str, Callable[..., Iterator[tuple[int, str]]]]] = [(IMPORT_NOT_TOP, _check_imports_at_top)]
    if is_test_file(rel):
        rules += _TEST_RULES
    out = [
        Violation(path=rel, line=line, rule=rule, message=message)
        for rule, check in rules
        for line, message in check(tree=tree)
        if not _waived(source_lines=source_lines, line=line, rule=rule)
    ]
    out.sort(key=lambda v: (v.line, v.rule))
    counts = FileCounts(rel=rel, text=len(_text_line_numbers(source=source, tree=tree)), total=len(source_lines))
    return out, counts


def _git(args: list[str], *, cwd: Path) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise ConfigError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def changed_py_files(*, base_ref: str, repo_root: Path) -> list[str]:
    """PR-modified .py files: merge-base committed diff plus working-tree edits."""
    out: set[str] = set()
    for target in (f"{base_ref}...HEAD", "HEAD"):
        listing = _git(["diff", "--name-only", "--diff-filter=ACMR", target], cwd=repo_root)
        out.update(p for p in listing.splitlines() if p.endswith(".py"))
    return sorted(out)


def _resolve_base_ref(*, pr: str | None, repo: str | None, base: str | None, repo_root: Path) -> str:
    """`origin/<branch>` for --base, or for the PR's base branch; best-effort fetch first."""
    if base is None:
        cmd = ["gh", "pr", "view", str(pr), "--json", "baseRefName", "--jq", ".baseRefName"]
        if repo:
            cmd += ["--repo", repo]
        proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=False)
        base = proc.stdout.strip()
        if proc.returncode != 0 or not base:
            raise ConfigError(f"could not resolve the base branch of PR {pr}")
    subprocess.run(["git", "fetch", "origin", base, "--quiet"], cwd=repo_root, capture_output=True, check=False)
    ref = f"origin/{base}"
    _git(["rev-parse", "--verify", "--quiet", ref], cwd=repo_root)
    return ref


def _ratio_report(groups: dict[str, list[FileCounts]], *, cap_pct: float) -> bool:
    """Print per-group ratios; True when any group exceeds the cap."""
    red = False
    for group, files in groups.items():
        text = sum(f.text for f in files)
        total = sum(f.total for f in files)
        if not total:
            continue
        pct = 100.0 * text / total
        print(f"check-conventions: {group} text-only ratio {pct:.1f}% ({text}/{total}, cap {cap_pct:.1f}%)",
              file=sys.stderr)
        if pct <= cap_pct:
            continue
        red = True
        print(f"[{TEXT_RATIO}] {group}: text-only lines are {pct:.1f}% of the changed {group} files"
              f" ({text}/{total}), cap {cap_pct:.1f}%")
        for f in sorted((f for f in files if f.total), key=lambda f: f.text / f.total, reverse=True):
            print(f"    {f.rel}: {100.0 * f.text / f.total:.1f}% ({f.text}/{f.total})")
    return red


def run(*, rels: list[str], repo_root: Path, excludes: list[str], cap_pct: float) -> int:
    exempt = [r for r in rels if _is_excluded(r, patterns=excludes)]
    rels = [r for r in rels if not _is_excluded(r, patterns=excludes)]
    if exempt:
        print(f"check-conventions: exempt, skipped: {', '.join(exempt)}", file=sys.stderr)
    violations: list[Violation] = []
    groups: dict[str, list[FileCounts]] = {"source": [], "tests": []}
    for rel in rels:
        path = repo_root / rel
        if not path.exists():
            continue
        file_violations, counts = check_file(path, rel=rel)
        violations.extend(file_violations)
        if counts is not None:
            groups["tests" if is_test_file(rel) else "source"].append(counts)
    for v in violations:
        print(v.render())
    ratio_red = _ratio_report(groups, cap_pct=cap_pct)
    print(f"check-conventions: {len(violations)} violation(s) across {len(rels)} changed .py file(s)",
          file=sys.stderr)
    return 1 if violations or ratio_red else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="la-check-conventions", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pr", nargs="?", help="PR number (resolves the base branch)")
    parser.add_argument("--repo", help="OWNER/REPO for the PR lookup (default: current repo)")
    parser.add_argument("--base", help="base branch; skips the PR lookup")
    parser.add_argument("--file", action="append", default=[], dest="files",
                        help="check this repo-relative file instead of the PR diff (repeatable)")
    parser.add_argument("--exclude", action="append", default=[], metavar="GLOB",
                        help="extra repo-relative glob exempt from all checks (repeatable)")
    parser.add_argument("--text-ratio-cap", type=float, help="percent cap (default: from config)")
    args = parser.parse_args(argv)
    if not (args.pr or args.base or args.files):
        parser.error("give a PR number, --base BRANCH, or --file")

    repo_root = find_repo_root(Path.cwd())
    try:
        config = load_config(repo_root)
        if args.files:
            rels = args.files
        else:
            base_ref = _resolve_base_ref(pr=args.pr, repo=args.repo, base=args.base, repo_root=repo_root)
            rels = changed_py_files(base_ref=base_ref, repo_root=repo_root)
    except ConfigError as exc:
        print(f"la-check-conventions: {exc}", file=sys.stderr)
        return 2
    cap = args.text_ratio_cap if args.text_ratio_cap is not None else config.conventions.text_ratio_max * 100
    status = run(rels=rels, repo_root=repo_root, excludes=[*config.conventions.exempt, *args.exclude], cap_pct=cap)
    if status == 0:
        print("gate: CLEAR — conventions hold on the PR's modified .py files.")
    else:
        print(GATE_RED_HINT)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
