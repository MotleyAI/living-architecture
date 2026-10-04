"""`la-check-conventions`: the deterministic conventions gate over a change's source files, every language."""

from __future__ import annotations

import fnmatch
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from living_architecture import lang
from living_architecture.config import ConfigError, load_config
from living_architecture.contract import conventions, glob_match, language_ids, message
from living_architecture.contract import language as registry
from living_architecture.conventions.facts import FactsError, collect, language_of

_FAILURES = ("unreadable", "syntax-error")


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


def is_test_file(rel: str) -> bool:
    lang_id = language_of(rel)
    if lang_id is None:
        return False
    return any(glob_match(g, Path(rel).as_posix()) for g in registry(lang_id)["test_globs"])


def _is_excluded(rel: str, *, patterns: list[str]) -> bool:
    rel_posix = Path(rel).as_posix()
    return any(fnmatch.fnmatch(rel_posix, pat) for pat in patterns)


def waived(*, text: str, rule: str, language: str) -> bool:
    """`text` (the flagged line) carries the language's waiver comment for `rule`."""
    if not conventions()["rules"].get(rule, {}).get("waivable"):
        return False
    pattern = re.escape(registry(language)["comment_prefix"]) + conventions()["waiver"]
    m = re.search(pattern, text)
    return bool(m and m.group(1) == rule)


def _present(languages: list[str]) -> list[str]:
    return [lang_id for lang_id in language_ids() if lang_id in languages]


def files_label(languages: list[str]) -> str:
    """Each present language's files label in language-id order, or the empty label."""
    labels = [registry(lang_id)["files_label"] for lang_id in _present(languages)]
    return message("conventions.label-separator").join(labels) if labels else message("conventions.empty-label")


def _waiver_examples(languages: list[str]) -> str:
    examples = [message("conventions.waiver-example", prefix=registry(lang_id)["comment_prefix"]) for lang_id in _present(languages)]
    return message("conventions.waiver-separator").join(examples)


def _violations(entry: dict[str, Any]) -> list[Violation]:
    rel = entry["path"]
    if entry["status"] in _FAILURES:
        return [Violation(path=rel, line=entry["line"], rule=entry["status"], message=entry["message"])]
    if entry["status"] != "ok":
        return []
    lang_id = language_of(rel) or ""
    rules = conventions()["rules"]
    test_file = is_test_file(rel)
    return [
        Violation(path=rel, line=d["line"], rule=d["rule"], message=message(d["message_id"], **d["values"]))
        for d in entry["detections"]
        if (test_file or not rules[d["rule"]]["tests_only"]) and not waived(text=d["text"], rule=d["rule"], language=lang_id)
    ]


def check_file(path: Path, *, rel: str) -> tuple[list[Violation], FileCounts | None]:
    """One native-language file's violations and text/total counts (None when it cannot be analysed)."""
    [entry] = lang.conventions_facts(path.parent, [path.name])
    entry = {**entry, "path": rel}
    counts = FileCounts(rel=rel, text=entry["text_lines"], total=entry["total_lines"]) if entry["status"] == "ok" else None
    return sorted(_violations(entry), key=lambda v: (v.line, v.rule)), counts


def _git(args: list[str], *, cwd: Path) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise ConfigError(detail or message("conventions.git-failed", args=" ".join(args)))
    return proc.stdout.decode("utf-8", "surrogateescape")


def changed_source_files(*, base_ref: str, repo_root: Path) -> list[str]:
    """Changed files with a known extension: merge-base committed diff plus working-tree edits, sorted."""
    out: set[str] = set()
    for target in (f"{base_ref}...HEAD", "HEAD"):
        listing = _git(["diff", "--name-only", "-z", "--diff-filter=ACMR", target], cwd=repo_root)
        out.update(p for p in listing.split("\0") if p and language_of(p) is not None)
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


def _select(rels: list[str], *, explicit: bool, excludes: list[str]) -> list[str]:
    """Known-extension, non-exempt paths; explicit unknown ones are warned about, exempt ones listed."""
    known = []
    for rel in rels:
        if language_of(rel) is not None:
            known.append(rel)
        elif explicit:
            print(message("conventions.unknown-extension", path=rel), file=sys.stderr)
    exempt = [r for r in known if _is_excluded(r, patterns=excludes)]
    if exempt:
        print(message("conventions.exempt", paths=", ".join(exempt)), file=sys.stderr)
    return [r for r in known if not _is_excluded(r, patterns=excludes)]


def report(rels: list[str], facts: dict[str, dict[str, Any]], *, cap_pct: float) -> int:
    """Violations in path order, the ratio groups, the summary and the verdict; the exit code."""
    violations: list[Violation] = []
    groups: dict[str, list[FileCounts]] = {"source": [], "tests": []}
    for rel in rels:
        entry = facts[rel]
        violations.extend(_violations(entry))
        if entry["status"] == "ok":
            counts = FileCounts(rel=rel, text=entry["text_lines"], total=entry["total_lines"])
            groups["tests" if is_test_file(rel) else "source"].append(counts)
    violations.sort(key=lambda v: (v.path, v.line, v.rule))
    for v in violations:
        print(v.render())
    ratio_red = _ratio_report(groups, cap_pct=cap_pct)
    languages = [language_of(rel) or "" for rel in rels]
    label = files_label(languages)
    print(message("conventions.summary", count=len(violations), files=len(rels), label=label), file=sys.stderr)
    status = 1 if violations or ratio_red else 0
    verdict = message("conventions.clear", label=label) if status == 0 else message("conventions.red", waivers=_waiver_examples(languages))
    print(verdict)
    return status


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
    """The gate end to end: resolve the changed files, collect their facts, print the report and verdict."""
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
    rels = _select(rels, explicit=bool(files), excludes=[*config.conventions.exempt, *excludes])
    try:
        facts = collect(rels, cwd=repo_root, repo_root=repo_root)
    except FactsError as exc:
        if str(exc):
            print(message("conventions.error", error=str(exc)), file=sys.stderr)
        return 2
    cap = cap_pct if cap_pct is not None else config.conventions.text_ratio_max * 100
    return report(rels, facts, cap_pct=cap)
