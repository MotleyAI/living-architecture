"""`la-arch-migrate`: convert the repo to the current format: merge a legacy model layout, convert the retired `arc42`
key format and stamp `format`, verified and all-or-nothing."""

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
    current_format,
    format_problem,
    is_version,
    read_committed,
    stamp_format,
)
from living_architecture.contract import YAMLError, config_file, load_yaml, message

_INDEX_REL = "architecture/index.yaml"


class MigrateError(Exception):
    """The repo cannot be migrated; nothing was written."""


class _Move(BaseModel):
    source: str
    target: str


class _Index(BaseModel):
    """`architecture/index.yaml` as text and as data; `data` is None when it is absent or not a mapping."""

    text: str | None
    data: dict[Any, Any] | None


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


def _read_index(root: Path) -> _Index:
    path = root / _INDEX_REL
    if not path.is_file():
        return _Index(text=None, data=None)
    try:
        text = _read_exact(path)
    except UnicodeDecodeError:
        return _Index(text=None, data=None)
    try:
        data = load_yaml(text)
    except YAMLError:
        data = None
    return _Index(text=text, data=data if isinstance(data, dict) else None)


def _cross_cutting(index: _Index) -> list[str]:
    entries = index.data.get("cross_cutting_arc42") if index.data else None
    return [e for e in entries if isinstance(e, str)] if isinstance(entries, list) else []


def _diagram_keys(index: _Index) -> list[Any]:
    diagrams = index.data.get("diagrams") if index.data else None
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


def _verify(root: Path, before: ModelParse, plan: _Plan, index: _Index, moved_entries: set[str]) -> None:
    """MigrateError unless the staged result parses like the input, apart from the converted arc42 format.

    A doc moves by rename, so it stays byte-identical by construction.
    """
    expected = (_comparable(_without_arc42(before)), parse_views(root, before))
    staged_index = plan.outputs.get(_INDEX_REL, index.text)
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        (staging / "architecture").mkdir()
        if staged_index is not None:
            (staging / _INDEX_REL).write_text(staged_index, encoding="utf-8", newline="")
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


def _index_as_expected(plan: _Plan, index: _Index, moved_entries: set[str]) -> bool:
    """The staged index parses to the input's, with only the planned renames."""
    written = plan.outputs.get(_INDEX_REL)
    if written is None or index.data is None:
        return True
    return load_yaml(written) == _expected_index(index.data, plan.renames, moved_entries)


class _Step(BaseModel):
    """One applied change: the path it touched, how to undo it, and whether the path is back as it was."""

    rel: str
    undo: Callable[[], object]
    restored: Callable[[], bool]


def _create_exclusive(root: Path, rel: str, text: str, steps: list[_Step]) -> None:
    """Create `rel` exclusively, journalled before the open so a half-made file is undone too."""
    path = root / rel
    steps.append(_Step(rel=rel, undo=lambda: path.unlink(missing_ok=True), restored=lambda: not os.path.lexists(path)))
    try:
        with path.open("x", encoding="utf-8", newline="") as out:
            out.write(text)
    except FileExistsError:
        steps.pop()
        raise


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _restore_file(path: Path, original: bytes, mode: int) -> None:
    path.write_bytes(original)
    path.chmod(mode)


def _restore_dir(path: Path, mode: int) -> None:
    path.mkdir()
    path.chmod(mode)


def _delete(root: Path, rel: str, original: bytes, steps: list[_Step]) -> None:
    path = root / rel
    mode = _mode(path)
    path.unlink()
    steps.append(
        _Step(
            rel=rel,
            undo=lambda: _restore_file(path, original, mode),
            restored=lambda: path.is_file() and _mode(path) == mode and path.read_bytes() == original,
        )
    )


def _remove_dir(root: Path, rel: str, steps: list[_Step]) -> None:
    path = root / rel
    mode = _mode(path)
    path.rmdir()
    steps.append(_Step(rel=rel, undo=lambda: _restore_dir(path, mode), restored=lambda: path.is_dir() and _mode(path) == mode))


def _swap_in(root: Path, rel: str, text: str, steps: list[_Step]) -> None:
    """Replace `rel` with `text` through a sibling temp file and an atomic rename, keeping its mode."""
    path = root / rel
    temp = posixpath.join(posixpath.dirname(rel), f".{path.name}.{secrets.token_hex(4)}.tmp")
    _create_exclusive(root, temp, text, steps)
    os.chmod(root / temp, _mode(path))
    os.replace(root / temp, path)


def _replace(root: Path, rel: str, text: str, steps: list[_Step]) -> None:
    """Replace `rel`, journalled so a rollback puts its bytes and mode back."""
    path = root / rel
    original, mode = path.read_bytes(), _mode(path)
    _swap_in(root, rel, text, steps)
    steps.append(
        _Step(
            rel=rel,
            undo=lambda: _restore_file(path, original, mode),
            restored=lambda: path.is_file() and _mode(path) == mode and path.read_bytes() == original,
        )
    )


def _move(root: Path, move: _Move, steps: list[_Step]) -> None:
    source, target = root / move.source, root / move.target
    os.rename(source, target)
    steps.append(
        _Step(
            rel=move.source,
            undo=lambda: os.rename(target, source),
            restored=lambda: source.is_file() and not os.path.lexists(target),
        )
    )


def _rollback(steps: list[_Step], error: OSError) -> MigrateError | None:
    """Undo `steps` in reverse; an error naming every path that could not be put back, None when all were."""
    for step in reversed(steps):
        with contextlib.suppress(OSError):
            step.undo()
    left = sorted({step.rel for step in steps if not step.restored()})
    if not left:
        return None
    return MigrateError(message("arch-migrate.rollback-failed", error=str(error), paths=", ".join(left)))


def _write(root: Path, plan: _Plan, stamped: str) -> list[str]:
    """Write the layout files, move the docs, delete the legacy files and an emptied model dir, replace the config
    last; all or nothing."""
    steps: list[_Step] = []
    deleted: list[str] = []
    model_dir = legacy_model_dir()
    try:
        for rel, text in plan.outputs.items():
            if rel in plan.created:
                _create_exclusive(root, rel, text, steps)
            else:
                _replace(root, rel, text, steps)
        for move in plan.moves:
            _move(root, move, steps)
        for rel, original in plan.legacy.items():
            _delete(root, rel, original, steps)
            deleted.append(rel)
        if plan.legacy and not any((root / model_dir).iterdir()):
            _remove_dir(root, model_dir, steps)
            deleted.append(model_dir)
        _swap_in(root, config_file(), stamped, steps)
    except OSError as exc:
        failure = _rollback(steps, exc)
        if failure is None:
            raise
        raise failure from exc
    report = [message("arch-migrate.written", path=rel) for rel in [*plan.outputs, config_file()]]
    report += [message("arch-migrate.moved", source=m.source, target=m.target) for m in plan.moves]
    return report + [message("arch-migrate.deleted", path=rel) for rel in deleted]


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
    if renames and index.text is not None:
        outputs[_INDEX_REL] = _renamed_index(index.text, renames)
    plan = _Plan(outputs=outputs, created=created, moves=moves, renames=renames, legacy=legacy)
    _verify(root, before, plan, index, {m.source for m in entry_moves})
    return plan


def _stamped(root: Path) -> str | None:
    """The stamped config text, or None when the repo already declares the current format."""
    try:
        committed = read_committed(root)
    except ConfigError as exc:
        raise MigrateError(str(exc)) from exc
    if committed is None:
        raise MigrateError(message("arch-migrate.no-config"))
    current = current_format()
    data = committed.data or {}
    if FORMAT_KEY in data:
        problem = format_problem(data)
        declared = data[FORMAT_KEY]
        if problem is not None and is_version(declared) and compare_versions(declared, current) < 0:
            raise MigrateError(message("arch-migrate.unknown-format", declared=declared, current=current))
        if problem is not None:
            raise MigrateError(problem)
        return None
    stamped = stamp_format(committed.text)
    if stamped is None:
        raise MigrateError(message("arch-migrate.stamp-mismatch", current=current))
    return stamped


def migrate(root: Path) -> list[str]:
    """Migrate the repo at `root`; the lines to print. MigrateError or OSError having changed nothing, unless named."""
    stamped = _stamped(root)
    if stamped is None:
        return [message("arch-migrate.nothing", current=current_format())]
    return _write(root, _plan(root), stamped)


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
