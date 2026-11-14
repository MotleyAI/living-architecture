"""`la-arch-migrate`: convert the repo to the current format one released format at a time and stamp `format`,
verified and all-or-nothing."""

from __future__ import annotations

import contextlib
import itertools
import os
import posixpath
import re
import secrets
import stat
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from living_architecture.c4.index import INDEX_REL, Index, load_index
from living_architecture.c4.layout import (
    ARCH_DIR,
    RETIRED_ARC42_KEY,
    WHITESPACE,
    FileScan,
    classify,
    element_doc,
    is_flat_doc,
    legacy_model_dir,
    model_file,
    sources,
    views_file,
)
from living_architecture.c4.model import (
    ModelParse,
    Pos,
    parse_model_files,
    parse_model_texts,
    strip_line_comment,
)
from living_architecture.c4.views import EMPTY_VIEWS, parse_views
from living_architecture.config import (
    FORMAT_KEY,
    ConfigError,
    compare_versions,
    format_problem,
    is_version,
    read_committed,
    released_formats,
    stamp_format,
)
from living_architecture.contract import config_file, load_yaml, message


class MigrateError(Exception):
    """The repo cannot be migrated; nothing was written."""


class _Move(BaseModel):
    source: str
    target: str


class _Plan(BaseModel):
    """What one run stages: new text per written path (in report order), doc moves, index renames, legacy files."""

    outputs: dict[str, str]
    created: set[str]
    moves: list[_Move]
    renames: dict[str, str]
    legacy: dict[str, bytes]


def _outside_lines(file_scan: FileScan) -> str:
    """The comment and blank lines outside every block; a comment sharing a line with a block keeps its own line."""
    text = file_scan.text
    pieces: list[str] = []
    pos = 0
    for block in file_scan.blocks:
        pieces += [text[pos : block.start], "\0"]
        pos = (block.close or len(text)) + 1
    pieces.append(text[pos:])
    lines = "".join(pieces).split("\n")
    if lines[-1] == "":
        lines.pop()
    kept: list[str] = []
    for line in lines:
        if "\0" not in line:
            kept.append(line + "\n")
        elif comment := line.replace("\0", "").strip(WHITESPACE):
            kept.append(comment + "\n")
    return "".join(kept)


def _interiors(scans: list[FileScan], kind: str) -> str:
    """The interior of every `kind` block, in file then block order; an empty block when there is none."""
    parts = [s.text[b.open + 1 : b.close] for s in scans for b in s.blocks if b.kind == kind]
    return "".join(parts) if parts else "\n"


def merged_model(scans: list[FileScan]) -> str:
    """The canonical `model.c4` text for the legacy files' scans, in sorted-file order."""
    head = "".join(_outside_lines(s) for s in scans)
    return f"{head}specification {{{_interiors(scans, 'specification')}}}\nmodel {{{_interiors(scans, 'model')}}}\n"


def _read_exact(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def _read_index(root: Path) -> Index | None:
    """The index, None when absent; MigrateError when it is unusable."""
    index = load_index(root)
    if isinstance(index, str):
        raise MigrateError(index)
    return index


def _cross_cutting(index: Index | None) -> list[str]:
    """The index's `cross_cutting_arc42` paths; empty without an index or that list."""
    entries = index.data.get("cross_cutting_arc42") if index is not None else None
    return [e for e in entries if isinstance(e, str)] if isinstance(entries, list) else []


def _diagram_keys(index: Index | None) -> list[Any]:
    """The keys of the index's `diagrams` mapping; empty without an index or that mapping."""
    diagrams = index.data.get("diagrams") if index is not None else None
    return list(diagrams) if isinstance(diagrams, dict) else []


def _strip_arc42(text: str, model: ModelParse) -> tuple[str, list[_Move]]:
    """`text` without each `arc42` statement (or the metadata block it alone fills), and the element doc moves,
    a doc already at its target included."""
    cuts: list[tuple[Pos, Pos]] = []
    moves: list[_Move] = []
    for element in model.elements:
        if RETIRED_ARC42_KEY not in element.metadata:
            continue
        span = model.spans[element.id]
        cuts.append(span.block if set(element.metadata) == {RETIRED_ARC42_KEY} else span.keys[RETIRED_ARC42_KEY])
        source = element.metadata[RETIRED_ARC42_KEY]
        if isinstance(source, str):
            moves.append(_Move(source=source, target=element_doc(element.id)))
    return _cut(text, cuts), moves


def _cut(text: str, spans: list[tuple[Pos, Pos]]) -> str:
    """`text` without each span: with its lines when nothing else is on them, else with the whitespace on one side."""
    lines = text.splitlines(keepends=True)
    starts = [0, *itertools.accumulate(len(line) for line in lines)]
    out: list[str] = []
    pos = 0
    for start, end in sorted(_cut_range(text, lines, starts, span) for span in spans):
        out.append(text[pos : max(pos, start)])
        pos = max(pos, end)
    return "".join(out) + text[pos:]


def _cut_range(text: str, lines: list[str], starts: list[int], span: tuple[Pos, Pos]) -> tuple[int, int]:
    (first, first_col), (last, last_col) = span
    start, end = starts[first] + first_col, starts[last] + last_col
    before = text[starts[first] : start]
    after = text[end : starts[last] + len(lines[last].splitlines()[0])]
    if not before.strip(WHITESPACE) and not strip_line_comment(after).strip(WHITESPACE):
        return starts[first], starts[last + 1]
    if not before.strip(WHITESPACE):
        return start, end + len(after) - len(after.lstrip(WHITESPACE))
    return start - (len(before) - len(before.rstrip(WHITESPACE))), end


def _flattened(entries: list[str]) -> list[_Move]:
    targets = [(e, f"{ARCH_DIR}{posixpath.basename(e)}") for e in entries if not is_flat_doc(e)]
    return [_Move(source=e, target=t) for e, t in targets if t != e]


def _contained(rel: str) -> bool:
    """`rel` is a relative path that stays inside the repo."""
    path = Path(rel)
    return bool(rel) and not path.is_absolute() and ".." not in path.parts


def _refusal(root: Path, moves: list[_Move], diagram_keys: list[Any]) -> str | None:
    """The first refused move's message, in plan order and check order; a doc already at its target claims its path."""
    targets_of: dict[str, str] = {}
    sources_of: dict[str, str] = {}
    for move in moves:
        source, target = move.source, move.target
        if not _contained(source) or not (root / source).is_file():
            return message("arch-migrate.source-missing", source=source)
        if source in targets_of:
            return message("arch-migrate.source-moved-twice", source=source, first=targets_of[source], second=target)
        if target in sources_of:
            return message("arch-migrate.shared-target", first=sources_of[target], second=source, target=target)
        if source != target and os.path.lexists(root / target):
            return message("arch-migrate.target-taken", source=source, target=target)
        if source != target and target in diagram_keys:
            return message("arch-migrate.diagrams-key-taken", source=source, target=target)
        targets_of[source] = target
        sources_of[target] = source
    return None


def _code_end(line: str) -> int:
    """Where a YAML line's comment starts (outside quotes, after whitespace or at the start), else its length."""
    quote = ""
    for i, ch in enumerate(line):
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return i
    return len(line)


def _renamed_index(text: str, renames: dict[str, str]) -> str:
    """`text` with every scalar token equal to a rename source, outside comments, replaced by its target."""
    patterns = [
        (re.compile(rf"(?<![^\s\[{{,'\"]){re.escape(source)}(?![^\s\]}},:'\"])"), target)
        for source, target in renames.items()
    ]
    out: list[str] = []
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        end = _code_end(body)
        code = body[:end]
        for pattern, target in patterns:
            code = pattern.sub(lambda _m, t=target: t, code)
        out.append(code + line[end:])
    return "".join(out)


def _expected_index(data: dict[Any, Any], renames: dict[str, str], moved_entries: set[str]) -> dict[Any, Any]:
    """`data` with the moved cross-cutting entries and the moved diagrams keys renamed."""
    expected = dict(data)
    entries = data.get("cross_cutting_arc42")
    if isinstance(entries, list):
        expected["cross_cutting_arc42"] = [renames[e] if isinstance(e, str) and e in moved_entries else e for e in entries]
    diagrams = data.get("diagrams")
    if isinstance(diagrams, dict):
        expected["diagrams"] = {renames.get(k, k) if isinstance(k, str) else k: v for k, v in diagrams.items()}
    return expected


def _comparable(model: ModelParse) -> dict[str, Any]:
    """`model` without line spans, its findings as sorted multisets (merging spec blocks may reorder them)."""
    dump = model.model_dump(exclude={"spans"})
    dump["findings"] = sorted(dump["findings"])
    dump["metadata_findings"] = sorted(dump["metadata_findings"])
    return dump


def _without_arc42(model: ModelParse) -> ModelParse:
    """`model` as it reads once every `arc42` key, and every metadata block left empty, is gone."""
    elements = []
    for element in model.elements:
        if RETIRED_ARC42_KEY in element.metadata:
            metadata = {k: v for k, v in element.metadata.items() if k != RETIRED_ARC42_KEY}
            element = element.model_copy(update={"metadata": metadata, "has_metadata": bool(metadata)})
        elements.append(element)
    return model.model_copy(update={"elements": elements})


def _verify(root: Path, before: ModelParse, plan: _Plan, index: Index | None, moved_entries: set[str]) -> None:
    """MigrateError unless the staged result parses like the input, apart from the converted arc42 format.

    A doc moves by rename, so it stays byte-identical by construction.
    """
    expected = (_comparable(_without_arc42(before)), parse_views(root, before))
    staged_index = plan.outputs.get(INDEX_REL, index.text if index is not None else None)
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        (staging / "architecture").mkdir()
        if staged_index is not None:
            (staging / INDEX_REL).write_text(staged_index, encoding="utf-8", newline="")
        views = root / views_file()
        if views_file() in plan.outputs:
            (staging / views_file()).write_text(plan.outputs[views_file()], encoding="utf-8", newline="")
        elif views.is_file():
            (staging / views_file()).write_bytes(views.read_bytes())
        model_text = plan.outputs.get(model_file())
        staged_model = parse_model_texts([_read_exact(root / model_file()) if model_text is None else model_text])
        after = (_comparable(staged_model), parse_views(staging, staged_model))
    if expected != after or not _index_as_expected(plan, index, moved_entries):
        raise MigrateError(message("arch-migrate.mismatch"))


def _index_as_expected(plan: _Plan, index: Index | None, moved_entries: set[str]) -> bool:
    """The staged index parses to the input's, with only the planned renames."""
    written = plan.outputs.get(INDEX_REL)
    if written is None or index is None:
        return True
    return load_yaml(written) == _expected_index(index.data, plan.renames, moved_entries)


class _State(BaseModel):
    """A path's state: a file's bytes and mode, a directory's mode, or absent (both None)."""

    data: bytes | None = None
    mode: int | None = None
    is_dir: bool = False


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _state(path: Path) -> _State:
    if path.is_dir():
        return _State(mode=_mode(path), is_dir=True)
    if os.path.lexists(path):
        return _State(data=path.read_bytes(), mode=_mode(path))
    return _State()


def _restore(path: Path, state: _State) -> None:
    """Put a file or directory back with its bytes and mode, over a read-only file too."""
    if state.is_dir:
        path.mkdir()
    else:
        if path.is_file():
            path.chmod(_mode(path) | stat.S_IWUSR)
        path.write_bytes(state.data or b"")
    if state.mode is not None:
        path.chmod(state.mode)


def _restored(path: Path, state: _State) -> bool:
    """Whether `path` is verifiably back in `state`."""
    try:
        return _state(path) == state
    except OSError:
        return False


class _Held(BaseModel):
    """The file at a path: its path before the run (None when the run created it) and whether the run wrote it."""

    origin: str | None
    written: bool


class Transaction:
    """The filesystem changes of one run, all undone on any failure, and their net effect."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._undo: list[Callable[[], object]] = []
        self._first: dict[str, _State] = {}
        self._held: dict[str, _Held | None] = {}
        self._written: list[str] = []
        self._moved: list[str] = []
        self._vacated: list[str] = []

    @property
    def root(self) -> Path:
        return self._root

    def _touch(self, rel: str) -> Path:
        path = self._root / rel
        if rel not in self._first:
            self._first[rel] = _state(path)
        return path

    def _holder(self, rel: str) -> _Held | None:
        if rel in self._held:
            return self._held[rel]
        return _Held(origin=rel, written=False) if os.path.lexists(self._root / rel) else None

    def _wrote(self, rel: str, held: _Held | None) -> None:
        self._held[rel] = _Held(origin=held.origin if held else None, written=True)
        if rel not in self._written:
            self._written.append(rel)

    def _create_exclusive(self, rel: str, text: str) -> None:
        """Create `rel` exclusively, journalled before the open so a half-made file is undone too."""
        path = self._touch(rel)
        self._undo.append(lambda: path.unlink(missing_ok=True))
        try:
            with path.open("x", encoding="utf-8", newline="") as out:
                out.write(text)
        except FileExistsError:
            self._undo.pop()
            raise

    def create(self, rel: str, text: str) -> None:
        """Create the new file `rel`."""
        held = self._holder(rel)
        self._create_exclusive(rel, text)
        self._wrote(rel, held)

    def replace(self, rel: str, text: str) -> None:
        """Replace `rel` through a sibling temp file and an atomic rename, keeping its mode."""
        held = self._holder(rel)
        path = self._touch(rel)
        original = _state(path)
        temp = posixpath.join(posixpath.dirname(rel), f".{path.name}.{secrets.token_hex(4)}.tmp")
        self._create_exclusive(temp, text)
        os.chmod(self._root / temp, _mode(path))
        os.replace(self._root / temp, path)
        self._undo.append(lambda: _restore(path, original))
        self._wrote(rel, held)

    def move(self, source: str, target: str) -> None:
        """Move the file `source` to the free path `target`."""
        held = self._holder(source)
        source_path, target_path = self._touch(source), self._touch(target)
        os.rename(source_path, target_path)
        self._undo.append(lambda: os.rename(target_path, source_path))
        self._held[source] = None
        self._held[target] = held
        if held is not None and held.origin is not None and held.origin not in self._moved:
            self._moved.append(held.origin)
        if held is not None and held.written and target not in self._written:
            self._written.append(target)
        self._vacated.append(source)

    def delete(self, rel: str) -> None:
        """Delete the file `rel`."""
        path = self._touch(rel)
        original = _state(path)
        path.unlink()
        self._undo.append(lambda: _restore(path, original))
        self._held[rel] = None
        self._vacated.append(rel)

    def remove_dir(self, rel: str) -> None:
        """Remove the empty directory `rel`."""
        path = self._touch(rel)
        original = _state(path)
        path.rmdir()
        self._undo.append(lambda: _restore(path, original))
        self._held[rel] = None
        self._vacated.append(rel)

    def rollback(self, error: BaseException) -> MigrateError | None:
        """Undo every change in reverse; an error naming every path left changed, None when all were put back."""
        for undo in reversed(self._undo):
            with contextlib.suppress(OSError):
                undo()
        left = sorted(rel for rel, state in self._first.items() if not _restored(self._root / rel, state))
        if not left:
            return None
        return MigrateError(message("arch-migrate.rollback-failed", error=str(error), paths=", ".join(left)))

    def report(self, last: str) -> list[str]:
        """The net effect: written paths (`last` last), then composed moves, then deleted paths."""
        exists = {rel: os.path.lexists(self._root / rel) for rel in self._first}
        written = [rel for rel in self._written if exists[rel]]
        written = [rel for rel in written if rel != last] + [rel for rel in written if rel == last]
        final = {held.origin: rel for rel, held in self._held.items() if held is not None and held.origin is not None}
        moves = [(origin, final[origin]) for origin in self._moved if final.get(origin, origin) != origin]
        moved = {origin for origin, _ in moves}
        deleted: list[str] = []
        for rel in self._vacated:
            if self._first[rel] != _State() and not exists[rel] and rel not in moved and rel not in deleted:
                deleted.append(rel)
        return [
            *(message("arch-migrate.written", path=rel) for rel in written),
            *(message("arch-migrate.moved", source=source, target=target) for source, target in moves),
            *(message("arch-migrate.deleted", path=rel) for rel in deleted),
        ]


def _apply(plan: _Plan, tx: Transaction) -> None:
    """Write the layout files, move the docs, delete the legacy files and an emptied model dir."""
    for rel, text in plan.outputs.items():
        if rel in plan.created:
            tx.create(rel, text)
        else:
            tx.replace(rel, text)
    for move in plan.moves:
        tx.move(move.source, move.target)
    for rel in plan.legacy:
        tx.delete(rel)
    model_dir = legacy_model_dir()
    if plan.legacy and not any((tx.root / model_dir).iterdir()):
        tx.remove_dir(model_dir)


def _plan(root: Path) -> _Plan:
    """The layout and arc42 conversions to apply; none when there is no model to convert."""
    if not sources(root):
        return _Plan(outputs={}, created=set(), moves=[], renames={}, legacy={})
    layout = classify(root)
    if layout.state not in ("canonical", "legacy"):
        raise MigrateError(layout.message)
    legacy = {rel: (root / rel).read_bytes() for rel in layout.legacy_files}
    if legacy:
        before = parse_model_files([root / rel for rel in legacy])
        model_text = merged_model([layout.scans[rel] for rel in legacy])
    else:
        model_text = _read_exact(root / model_file())
        before = parse_model_texts([model_text])
    index = _read_index(root)
    stripped, element_moves = _strip_arc42(model_text, parse_model_texts([model_text]))
    entry_moves = _flattened(_cross_cutting(index))
    moves = element_moves + entry_moves
    keys = _diagram_keys(index)
    refusal = _refusal(root, moves, keys)
    if refusal is not None:
        raise MigrateError(refusal)
    moves = [m for m in moves if m.source != m.target]
    renamed = {m.source for m in entry_moves} | {k for k in keys if isinstance(k, str)}
    renames = {m.source: m.target for m in moves if m.source in renamed}
    outputs: dict[str, str] = {}
    created: set[str] = set()
    if legacy or stripped != model_text:
        outputs[model_file()] = stripped
    if legacy:
        created.add(model_file())
        if not layout.views_exists:
            outputs[views_file()] = EMPTY_VIEWS
            created.add(views_file())
    if renames and index is not None:
        outputs[INDEX_REL] = _renamed_index(index.text, renames)
    plan = _Plan(outputs=outputs, created=created, moves=moves, renames=renames, legacy=legacy)
    _verify(root, before, plan, index, {m.source for m in entry_moves})
    return plan


class MigrationStep(BaseModel):
    """One conversion: from the `source` format (None: a repo that declares none) to the `target` format."""

    source: str | None
    target: str
    apply: Callable[[Path, Transaction], None]


def _unversioned(root: Path, tx: Transaction) -> None:
    """The legacy layout and the retired arc42 key converted."""
    _apply(_plan(root), tx)


STEPS = [MigrationStep(source=None, target="0.4.0", apply=_unversioned)]


def _declared(root: Path, formats: list[str]) -> tuple[str | None, str] | None:
    """The declared format (None when absent) and the config text; None when it is current; MigrateError when it
    cannot be migrated."""
    try:
        committed = read_committed(root)
    except ConfigError as exc:
        raise MigrateError(str(exc)) from exc
    if committed is None:
        raise MigrateError(message("arch-migrate.no-config"))
    data = committed.data or {}
    if FORMAT_KEY not in data:
        return None, committed.text
    current, declared = formats[-1], data[FORMAT_KEY]
    problem = format_problem(data, current)
    if problem is None:
        return None
    if not is_version(declared) or compare_versions(declared, current) > 0:
        raise MigrateError(problem)
    if declared not in formats:
        raise MigrateError(message("arch-migrate.unknown-format", declared=declared, current=current))
    return declared, committed.text


def migrate(root: Path, steps: list[MigrationStep] | None = None, formats: list[str] | None = None) -> list[str]:
    """Migrate the repo at `root` through `steps` (default: STEPS) up to the last of `formats` (default: the released
    ones); the lines to print. MigrateError or OSError having changed nothing, unless named."""
    formats = formats or released_formats()
    current = formats[-1]
    found = _declared(root, formats)
    if found is None:
        return [message("arch-migrate.nothing", current=current)]
    declared, text = found
    stamped = stamp_format(text, current)
    if stamped is None:
        raise MigrateError(message("arch-migrate.stamp-mismatch", current=current))
    by_source = {step.source: step for step in steps or STEPS}
    sources = [None, *formats[:-1]] if declared is None else formats[formats.index(declared) : -1]
    tx = Transaction(root)
    try:
        for source in sources:
            by_source[source].apply(root, tx)
        tx.replace(config_file(), stamped)
    except Exception as exc:
        failure = tx.rollback(exc)
        if failure is None:
            raise
        raise failure from exc
    return tx.report(config_file())


def run(root: Path) -> int:
    """`la-arch-migrate`: print each written, moved and deleted path, or exit 2 having changed nothing."""
    try:
        report = migrate(root)
    except (MigrateError, OSError) as exc:
        print(message("arch-migrate.error", error=str(exc)), file=sys.stderr)
        return 2
    for line in report:
        print(line)
    return 0
