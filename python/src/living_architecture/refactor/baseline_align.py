"""A Python refactor keeps `.basedpyright/baseline.json` aligned: each entry basedpyright matches follows the
refactor's edits, moved files and moved declarations."""

from __future__ import annotations

import difflib
import json
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict
from rope.base.fscommands import read_str_coding

from living_architecture.config import ConfigError, find_repo_root, load_config
from living_architecture.contract import language, message
from living_architecture.lang.language_server import utf16_index, utf16_position
from living_architecture.refactor.position_map import Edit, map_range
from living_architecture.refactor.progress import checker_cause
from living_architecture.refactor.writer import FileMove, FileWrite
from living_architecture.typecheck import CommandError, python_diagnostics

Key = tuple[str, int, int, int, int]
"""A diagnostic: its rule and its 0-based start and end line and column."""


class BaselineFailed(Exception):
    """The configured checker failed, so the baseline cannot be realigned; `cause` is its cause's lines (none for an
    unreadable baseline)."""

    def __init__(self, cause: list[str] | None = None) -> None:
        super().__init__()
        self.cause = cause or []


def _failed(exc: CommandError) -> BaselineFailed:
    return BaselineFailed(checker_cause(exc.kind, exc.error, exc.code, exc.stderr))


class Aligned(BaseModel):
    """The baseline's new text, as a write and a printed diff (none when unchanged), and the entries that could not
    follow."""

    model_config = ConfigDict(frozen=True)

    write: FileWrite | None
    description: str
    warnings: tuple[str, ...]


def _decode(data: bytes) -> str:
    return data.decode(read_str_coding(data) or "utf-8")


def _starts(lines: list[str]) -> list[int]:
    out = [0]
    for line in lines:
        out.append(out[-1] + len(line))
    return out


def text_edits(old: str, new: str) -> list[Edit]:
    """Edits turning `old` into `new`: the changed lines, then the characters within them."""
    old_lines, new_lines = old.splitlines(True), new.splitlines(True)
    old_at, new_at = _starts(old_lines), _starts(new_lines)
    out: list[Edit] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        a, b = old[old_at[i1] : old_at[i2]], new[new_at[j1] : new_at[j2]]
        for inner, a1, a2, b1, b2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if inner != "equal":
                out.append((old_at[i1] + a1, old_at[i1] + a2, b2 - b1))
    return out


def _blocks(old: str, new: str) -> tuple[list[tuple[int, int, str]], list[tuple[int, str]]]:
    """The line blocks `new` drops from `old` (span, text) and the ones it adds (offset, text)."""
    old_lines, new_lines = old.splitlines(True), new.splitlines(True)
    old_at, new_at = _starts(old_lines), _starts(new_lines)
    removed: list[tuple[int, int, str]] = []
    added: list[tuple[int, str]] = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_opcodes():
        if tag in ("delete", "replace"):
            removed.append((old_at[i1], old_at[i2], old[old_at[i1] : old_at[i2]]))
        if tag in ("insert", "replace"):
            added.append((new_at[j1], new[new_at[j1] : new_at[j2]]))
    return removed, added


class _Files:
    """Every file the refactor touches, repo-relative: old and new text, edits, the new path, and with moved code
    the blocks it drops and adds."""

    def __init__(self, repo: Path, project: Path, writes: list[FileWrite], moves: list[FileMove],
                 edits: dict[str, list[Edit]] | None, moved_code: bool) -> None:
        self.repo = repo
        self.old: dict[str, str] = {}
        self.new: dict[str, str] = {}
        self.edits: dict[str, list[Edit]] = {}
        self.moves = [(self._rel(project / m.rel), self._rel(project / m.dest)) for m in moves]
        for w in writes:
            rel = self._rel(project / w.rel)
            self.old[rel] = _decode(w.old) if w.old is not None else ""
            self.new[rel] = _decode(w.new)
            given = (edits or {}).get(w.rel)
            self.edits[rel] = given if given is not None else text_edits(self.old[rel], self.new[rel])
        self.removed: dict[str, list[tuple[int, int, str]]] = {}
        self.added: dict[str, list[tuple[int, str]]] = {}
        if moved_code:
            for rel in self.old:
                self.removed[rel], self.added[rel] = _blocks(self.old[rel], self.new[rel])

    def _rel(self, path: Path) -> str:
        return Path(path).resolve().relative_to(self.repo).as_posix()

    def renamed(self, rel: str) -> str:
        for src, dest in self.moves:
            if rel == src or rel.startswith(f"{src}/"):
                return dest + rel[len(src) :]
        return rel

    def touched(self, rel: str) -> bool:
        return rel in self.old or self.renamed(rel) != rel

    def old_text(self, rel: str) -> str:
        if rel not in self.old:
            self.old[rel] = _decode((self.repo / rel).read_bytes())
        return self.old[rel]

    def new_text(self, rel: str) -> str:
        """The text of `rel` (a new path) after the refactor."""
        source = next((old for old in self.new if self.renamed(old) == rel), None)
        if source is not None:
            return self.new[source]
        return self.old_text(next((old for old in self.old if self.renamed(old) == rel), rel))

    def map(self, rel: str, start: int, end: int) -> tuple[str, int, int] | None:
        """`start:end` of `rel` after the refactor, with its new path; None when it cannot follow."""
        for s, e, text in self.removed.get(rel, ()):
            if s <= start < e or s < end <= e:
                if not (s <= start and end <= e):
                    return None
                dest = self._landing(rel, text)
                if dest is None:
                    break
                to, at, landed = dest
                ns, ne = map_range(text_edits(text, landed), start - s, end - s)
                return to, at + ns, at + ne
        ns, ne = map_range(self.edits.get(rel, []), start, end)
        if ns == ne and start < end:
            return None
        return self.renamed(rel), ns, ne

    def _landing(self, rel: str, text: str) -> tuple[str, int, str] | None:
        """The block another file adds that best matches `text`, dropped from `rel`."""
        best: tuple[float, str, int, str] | None = None
        for other, blocks in self.added.items():
            if other == rel:
                continue
            for at, added in blocks:
                ratio = difflib.SequenceMatcher(None, text, added, autojunk=False).ratio()
                if ratio > 0.5 and (best is None or ratio > best[0]):
                    best = (ratio, self.renamed(other), at, added)
        return None if best is None else best[1:]


def _diagnostics(report: dict[str, Any], repo: Path) -> list[tuple[str, Key]]:
    """The report's diagnostics in its order (each file's sorted by start, ties as the checker emits them)."""
    out: list[tuple[str, Key]] = []
    for d in report.get("generalDiagnostics", []):
        path = Path(d["file"]).resolve()
        if not path.is_relative_to(repo):
            continue
        r = d["range"]
        key = (str(d.get("rule", "")), r["start"]["line"], r["start"]["character"], r["end"]["line"], r["end"]["character"])
        out.append((path.relative_to(repo).as_posix(), key))
    return out


def _matches(entry: dict[str, Any], key: Key) -> bool:
    r = entry.get("range", {})
    count = r.get("lineCount")
    return (entry.get("code") == key[0] and r.get("startColumn") == key[2] and r.get("endColumn") == key[4]
            and (count is None or count == key[3] - key[1] + 1))


def _pairs(entries: list[dict[str, Any]], baselined: list[Key]) -> list[tuple[int, Key]]:
    """Each baselined diagnostic, in position order, with the first unpaired entry after the last one paired whose
    code, columns and line count equal it."""
    out: list[tuple[int, Key]] = []
    last = -1
    for key in baselined:
        k = next((i for i in range(last + 1, len(entries)) if _matches(entries[i], key)), None)
        if k is not None:
            out.append((k, key))
            last = k
    return out


def _run(repo: Path, command: str, baseline_text: str, files: list[str]) -> tuple[list[tuple[str, Key]], list[tuple[str, Key]]]:
    """The diagnostics of `files` with an empty baseline, and with a copy of the baseline."""
    with tempfile.TemporaryDirectory(prefix="la-baseline-") as tmp:
        empty, copy = Path(tmp) / "empty.json", Path(tmp) / "copy.json"
        empty.write_text('{"files": {}}', encoding="utf-8")
        copy.write_text(baseline_text, encoding="utf-8")
        try:
            everything = python_diagnostics(repo, command, ["--baselinefile", str(empty), *files])
            unbaselined = python_diagnostics(repo, command, ["--baselinefile", str(copy), *files])
        except CommandError as exc:
            raise _failed(exc) from None
    return _diagnostics(everything, repo), _diagnostics(unbaselined, repo)


def config_error(project: Path) -> str | None:
    """The config's error when the Python baseline file exists and the config cannot be read."""
    repo = find_repo_root(project.resolve()).resolve()
    if not (repo / language("python")["baseline_file"]).is_file():
        return None
    try:
        load_config(repo)
    except ConfigError as exc:
        return str(exc)
    return None


def baseline_runs(project: Path) -> bool:
    """The baseline phase runs: the Python checker command is set and its baseline file exists."""
    repo = find_repo_root(project.resolve()).resolve()
    try:
        command = load_config(repo).commands.typecheck.python
    except ConfigError:
        return False
    return command is not None and (repo / language("python")["baseline_file"]).is_file()


def probe(project: Path, source: Path) -> None:
    """Run the configured checker once on `source` against an empty baseline; `BaselineFailed` when it fails."""
    repo = find_repo_root(project.resolve()).resolve()
    found = _baseline(repo)
    if found is None:
        return
    with tempfile.TemporaryDirectory(prefix="la-baseline-") as tmp:
        empty = Path(tmp) / "empty.json"
        empty.write_text('{"files": {}}', encoding="utf-8")
        try:
            python_diagnostics(repo, found[0], ["--baselinefile", str(empty), str(source.resolve())])
        except CommandError as exc:
            raise _failed(exc) from None


class _Entry:
    def __init__(self, entry: dict[str, Any], position: tuple[int, int] | None) -> None:
        self.entry = entry
        self.position = position


def align(project: Path, writes: list[FileWrite], moves: list[FileMove], *, edits: dict[str, list[Edit]] | None = None,
          moved_code: bool = False) -> Aligned | None:
    """The baseline realigned through the refactor, without a write when only warnings remain; None when no checker,
    no baseline, no affected entry, or neither a change nor a warning; `BaselineFailed` when the checker fails."""
    project = project.resolve()
    repo = find_repo_root(project).resolve()
    found = _baseline(repo)
    if found is None:
        return None
    command, baseline_rel, raw, data, listed = found
    baseline_path = repo / baseline_rel
    files = _Files(repo, project, writes, moves, edits, moved_code)
    affected = sorted(key[2:] for key in listed if key.startswith("./") and files.touched(key[2:]))
    if not affected:
        return None
    everything, unbaselined = _run(repo, command, raw.decode("utf-8"), [rel for rel in affected if (repo / rel).is_file()])
    baselined_all = _baselined(everything, unbaselined)
    warnings: list[str] = []
    out = _realigned(listed, files, affected, baselined_all, baseline_rel, warnings)
    new_data = {**data, "files": {k: [e.entry for e in out[k]] for k in sorted(out) if out[k]}}
    if new_data == data:
        return Aligned(write=None, description="", warnings=tuple(warnings)) if warnings else None
    old_text = raw.decode("utf-8")
    new_text = json.dumps(new_data, indent=4)
    shown = Path(baseline_path).relative_to(project).as_posix() if baseline_path.is_relative_to(project) else str(baseline_path)
    description = "".join(difflib.unified_diff(old_text.splitlines(True), new_text.splitlines(True), f"a/{shown}", f"b/{shown}"))
    write = FileWrite(rel=shown, old=raw, new=new_text.encode("utf-8"))
    return Aligned(write=write, description=description, warnings=tuple(warnings))


def _baseline(repo: Path) -> tuple[str, str, bytes, dict[str, Any], dict[str, list[dict[str, Any]]]] | None:
    """The checker command, the baseline's path, bytes, data and file entries; None without a command or a
    baseline; `BaselineFailed` when unreadable."""
    try:
        command = load_config(repo).commands.typecheck.python
    except ConfigError:
        return None
    baseline_rel: str = language("python")["baseline_file"]
    baseline_path = repo / baseline_rel
    if command is None or not baseline_path.is_file():
        return None
    raw = baseline_path.read_bytes()
    try:
        data: dict[str, Any] = json.loads(raw)
        listed: dict[str, list[dict[str, Any]]] = data["files"]
    except (ValueError, KeyError, TypeError):
        raise BaselineFailed from None
    return command, baseline_rel, raw, data, listed


def _realigned(listed: dict[str, list[dict[str, Any]]], files: _Files, affected: list[str],
               baselined_all: list[tuple[str, Key]], baseline_rel: str, warnings: list[str]) -> dict[str, list[_Entry]]:
    """The entries by their file key after the refactor: each followed one moved to its new file and position."""
    out: dict[str, list[_Entry]] = {}
    moved_in: list[tuple[str, _Entry]] = []
    for key, entries in listed.items():
        rel = key.removeprefix("./")
        target = f"./{files.renamed(rel)}"
        mapped: dict[int, tuple[str, _Entry]] = {}
        if rel in affected:
            mapped = _followed(files, rel, entries, [k for path, k in baselined_all if path == rel], baseline_rel, warnings)
        bucket = out.setdefault(target, [])
        for index, entry in enumerate(entries):
            if index in mapped and mapped[index][0] != target:
                moved_in.append(mapped[index])
            else:
                bucket.append(mapped[index][1] if index in mapped else _Entry(entry, None))
    for target, entry in moved_in:
        _insert(out.setdefault(target, []), entry)
    return out


def _baselined(everything: list[tuple[str, Key]], unbaselined: list[tuple[str, Key]]) -> list[tuple[str, Key]]:
    """The diagnostics the baseline hides: those shown without it, less as many of each as it lets through."""
    shown_alone = Counter(unbaselined)
    out: list[tuple[str, Key]] = []
    for item in everything:
        if shown_alone[item]:
            shown_alone[item] -= 1
        else:
            out.append(item)
    return out


def _followed(files: _Files, rel: str, entries: list[dict[str, Any]], baselined: list[Key], baseline_rel: str,
              warnings: list[str]) -> dict[int, tuple[str, _Entry]]:
    """Each paired entry's index with where it goes after the refactor; a warning for each it cannot follow."""
    mapped: dict[int, tuple[str, _Entry]] = {}
    for index, diag in _pairs(entries, baselined):
        follow = _follow(files, rel, entries[index], diag)
        if follow is None:
            warnings.append(message("refactor.baseline-ambiguous", baseline=baseline_rel, code=entries[index].get("code"), path=rel))
        else:
            mapped[index] = follow
    return mapped


def _insert(bucket: list[_Entry], entry: _Entry) -> None:
    """`entry` before the first positioned entry after it."""
    at = next((i for i, e in enumerate(bucket) if e.position is not None and entry.position is not None
               and e.position > entry.position), len(bucket))
    bucket.insert(at, entry)


def _follow(files: _Files, rel: str, entry: dict[str, Any], diag: Key) -> tuple[str, _Entry] | None:
    """The entry of `diag` after the refactor, with its new file key."""
    old = files.old_text(rel)
    start, end = utf16_index(old, diag[1], diag[2]), utf16_index(old, diag[3], diag[4])
    mapped = files.map(rel, start, end)
    if mapped is None:
        return None
    to, ns, ne = mapped
    new = files.new_text(to)
    (sl, sc), (el, ec) = utf16_position(new, ns), utf16_position(new, ne)
    rng = dict(entry.get("range", {}))
    rng["startColumn"], rng["endColumn"] = sc, ec
    if "lineCount" in rng:
        rng["lineCount"] = el - sl + 1
    return f"./{to}", _Entry({**entry, "range": rng}, (sl, sc))
