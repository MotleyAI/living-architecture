"""`la-check-conventions`: the deterministic conventions gate over a change's source files."""

from __future__ import annotations

import fnmatch
import re
import subprocess
import sys
from functools import cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from living_architecture.config import ConfigError, load_config
from living_architecture.contract import conventions, glob_match, language, message
from living_architecture.lang import ParseFailure, analyze

LANGUAGE = "python"


class Violation(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    line: int
    rule: str
    message: str

    def render(self) -> str:
        return message("conventions.violation", path=self.path, line=self.line, rule=self.rule, message=self.message)


class FileCounts(BaseModel):
    model_config = ConfigDict(frozen=True)

    rel: str
    text: int
    total: int


@cache
def _waiver_re() -> re.Pattern[str]:
    return re.compile(re.escape(language(LANGUAGE)["comment_prefix"]) + conventions()["waiver"])


def is_test_file(rel: str) -> bool:
    return any(glob_match(g, Path(rel).as_posix()) for g in language(LANGUAGE)["test_globs"])


def _is_excluded(rel: str, *, patterns: list[str]) -> bool:
    rel_posix = Path(rel).as_posix()
    return any(fnmatch.fnmatch(rel_posix, pat) for pat in patterns)


def _waived(*, source_lines: list[str], line: int, rule: str) -> bool:
    if not 1 <= line <= len(source_lines) or not conventions()["rules"][rule]["waivable"]:
        return False
    m = _waiver_re().search(source_lines[line - 1])
    return bool(m and m.group(1) == rule)


def check_file(path: Path, *, rel: str) -> tuple[list[Violation], FileCounts | None]:
    """Violations plus text/total line counts (None when unreadable or unparsable)."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [Violation(path=rel, line=1, rule="unreadable", message=str(exc))], None
    try:
        analysis = analyze(source)
    except ParseFailure as exc:
        return [Violation(path=rel, line=exc.line, rule="syntax-error", message=exc.msg)], None
    source_lines = source.splitlines()
    rules = conventions()["rules"]
    test_file = is_test_file(rel)
    out = [
        Violation(path=rel, line=d.line, rule=d.rule, message=message(d.message_id, **d.values))
        for d in analysis.detections
        if (test_file or not rules[d.rule]["tests_only"])
        and not _waived(source_lines=source_lines, line=d.line, rule=d.rule)
    ]
    out.sort(key=lambda v: (v.line, v.rule))
    return out, FileCounts(rel=rel, text=analysis.text_lines, total=analysis.total_lines)


def _git(args: list[str], *, cwd: Path) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise ConfigError(proc.stderr.strip() or message("conventions.git-failed", args=" ".join(args)))
    return proc.stdout


def changed_source_files(*, base_ref: str, repo_root: Path) -> list[str]:
    """Changed source files: merge-base committed diff plus working-tree edits."""
    extensions = tuple(language(LANGUAGE)["source_extensions"])
    out: set[str] = set()
    for target in (f"{base_ref}...HEAD", "HEAD"):
        listing = _git(["diff", "--name-only", "--diff-filter=ACMR", target], cwd=repo_root)
        out.update(p for p in listing.splitlines() if p.endswith(extensions))
    return sorted(out)


def resolve_base_ref(*, pr: str | None, repo: str | None, base: str | None, repo_root: Path) -> str:
    """`origin/<branch>` for --base, or for the PR's base branch; best-effort fetch first."""
    if base is None:
        cmd = ["gh", "pr", "view", str(pr), "--json", "baseRefName", "--jq", ".baseRefName"]
        if repo:
            cmd += ["--repo", repo]
        proc = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True, check=False)
        base = proc.stdout.strip()
        if proc.returncode != 0 or not base:
            raise ConfigError(message("conventions.pr-base-unresolved", pr=pr))
    subprocess.run(["git", "fetch", "origin", base, "--quiet"], cwd=repo_root, capture_output=True, check=False)
    ref = f"origin/{base}"
    _git(["rev-parse", "--verify", "--quiet", ref], cwd=repo_root)
    return ref


def _pct(text: int, total: int) -> str:
    return f"{100.0 * text / total:.1f}"


def _ratio_report(groups: dict[str, list[FileCounts]], *, cap_pct: float) -> bool:
    """Print per-group ratios; True when any group exceeds the cap."""
    red = False
    cap = f"{cap_pct:.1f}"
    for group, files in groups.items():
        text = sum(f.text for f in files)
        total = sum(f.total for f in files)
        if not total:
            continue
        pct = 100.0 * text / total
        values = {"group": group, "pct": _pct(text, total), "text": text, "total": total, "cap": cap}
        print(message("conventions.ratio", **values), file=sys.stderr)
        if pct <= cap_pct:
            continue
        red = True
        print(message("conventions.ratio-over", **values))
        for f in sorted((f for f in files if f.total), key=lambda f: f.text / f.total, reverse=True):
            print(message("conventions.ratio-file", path=f.rel, pct=_pct(f.text, f.total), text=f.text, total=f.total))
    return red


def run(*, rels: list[str], repo_root: Path, excludes: list[str], cap_pct: float) -> int:
    exempt = [r for r in rels if _is_excluded(r, patterns=excludes)]
    rels = [r for r in rels if not _is_excluded(r, patterns=excludes)]
    if exempt:
        print(message("conventions.exempt", paths=", ".join(exempt)), file=sys.stderr)
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
    label = language(LANGUAGE)["files_label"]
    print(message("conventions.summary", count=len(violations), files=len(rels), label=label), file=sys.stderr)
    return 1 if violations or ratio_red else 0


def check_conventions(
    *,
    repo_root: Path,
    pr: str | None,
    repo: str | None,
    base: str | None,
    files: list[str],
    excludes: list[str],
    cap_pct: float | None,
) -> int:
    """The gate end to end: resolve the changed files, check them, print the verdict."""
    try:
        config = load_config(repo_root)
        if files:
            rels = files
        else:
            base_ref = resolve_base_ref(pr=pr, repo=repo, base=base, repo_root=repo_root)
            rels = changed_source_files(base_ref=base_ref, repo_root=repo_root)
    except ConfigError as exc:
        print(message("conventions.error", error=str(exc)), file=sys.stderr)
        return 2
    cap = cap_pct if cap_pct is not None else config.conventions.text_ratio_max * 100
    status = run(rels=rels, repo_root=repo_root, excludes=[*config.conventions.exempt, *excludes], cap_pct=cap)
    label = language(LANGUAGE)["files_label"]
    print(message("conventions.clear", label=label) if status == 0 else message("conventions.red"))
    return status
