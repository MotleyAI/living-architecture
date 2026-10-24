"""`la-arch-migrate`: merge the legacy `architecture/model/*.c4` model into `architecture/model.c4` and convert the
retired `arc42` key format, verified and all-or-nothing."""

from __future__ import annotations

import contextlib
import os
import posixpath
import re
import sys
import tempfile
import uuid
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
    views_file,
)
from living_architecture.c4.model import ModelParse, parse_model_files, parse_model_texts
from living_architecture.c4.views import EMPTY_VIEWS, parse_views
from living_architecture.contract import YAMLError, load_yaml, message

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
    """What one run stages: new text per written path (in report order), doc moves, index renames."""

    outputs: dict[str, str]
    created: set[str]
    moves: list[_Move]
    renames: dict[str, str]


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
    text = _read_exact(path)
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
    """`text` without each `arc42` line (and each metadata block it empties), and the element doc moves."""
    drop: set[int] = set()
    moves: list[_Move] = []
    for element in model.elements:
        if RETIRED_ARC42_KEY not in element.metadata:
            continue
        span = model.spans[element.id]
        first, last = span.keys[RETIRED_ARC42_KEY]
        drop.update(range(first, last + 1))
        if set(element.metadata) == {RETIRED_ARC42_KEY}:
            drop.update(range(span.block[0], span.block[1] + 1))
        source = element.metadata[RETIRED_ARC42_KEY]
        if isinstance(source, str) and source != element_doc(element.id):
            moves.append(_Move(source=source, target=element_doc(element.id)))
    lines = text.splitlines(keepends=True)
    return "".join(line for i, line in enumerate(lines) if i not in drop), moves


def _flattened(entries: list[str]) -> list[_Move]:
    targets = [(e, f"{ARCH_DIR}{posixpath.basename(e)}") for e in entries if not is_flat_doc(e)]
    return [_Move(source=e, target=t) for e, t in targets if t != e]


def _contained(rel: str) -> bool:
    """`rel` is a relative path that stays inside the repo."""
    path = Path(rel)
    return bool(rel) and not path.is_absolute() and ".." not in path.parts


def _refusal(root: Path, moves: list[_Move], diagram_keys: list[Any]) -> str | None:
    """The first refused move's message, in plan order and check order."""
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
        if os.path.lexists(root / target):
            return message("arch-migrate.target-taken", source=source, target=target)
        if target in diagram_keys:
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
        expected["cross_cutting_arc42"] = [renames[e] if e in moved_entries else e for e in entries]
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


class _Commit:
    """Filesystem changes with an undo log; `rollback` restores every touched path byte-for-byte."""

    def __init__(self) -> None:
        self.undo: list[Callable[[], object]] = []

    def create(self, path: Path, text: str) -> None:
        self.undo.append(path.unlink)
        try:
            with path.open("x", encoding="utf-8", newline="") as out:
                out.write(text)
        except FileExistsError:
            self.undo.pop()
            raise

    def replace(self, path: Path, text: str) -> None:
        original = path.read_bytes()
        temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        self.create(temp, text)
        os.replace(temp, path)
        self.undo.append(lambda: path.write_bytes(original))

    def move(self, source: Path, target: Path) -> None:
        os.rename(source, target)
        self.undo.append(lambda: os.rename(target, source))

    def delete(self, path: Path) -> None:
        original = path.read_bytes()
        path.unlink()
        self.undo.append(lambda: path.write_bytes(original))

    def rmdir(self, path: Path) -> None:
        path.rmdir()
        self.undo.append(path.mkdir)

    def rollback(self) -> None:
        for undo in reversed(self.undo):
            with contextlib.suppress(OSError):
                undo()


def _write(root: Path, plan: _Plan, legacy: list[str]) -> list[str]:
    """Write the outputs, move the docs, delete the legacy files and an emptied model dir; undo it all on an OSError."""
    commit = _Commit()
    model_dir = root / legacy_model_dir()
    removed_dir = False
    try:
        for rel, text in plan.outputs.items():
            if rel in plan.created:
                commit.create(root / rel, text)
            else:
                commit.replace(root / rel, text)
        for move in plan.moves:
            commit.move(root / move.source, root / move.target)
        for rel in legacy:
            commit.delete(root / rel)
        if legacy and not any(model_dir.iterdir()):
            commit.rmdir(model_dir)
            removed_dir = True
    except OSError:
        commit.rollback()
        raise
    report = [message("arch-migrate.written", path=rel) for rel in plan.outputs]
    report += [message("arch-migrate.moved", source=m.source, target=m.target) for m in plan.moves]
    report += [message("arch-migrate.deleted", path=rel) for rel in legacy]
    if removed_dir:
        report.append(message("arch-migrate.deleted", path=legacy_model_dir()))
    return report


def migrate(root: Path) -> list[str]:
    """Migrate the repo at `root`; the lines to print. MigrateError or OSError when nothing was written."""
    layout = classify(root)
    if layout.state not in ("canonical", "legacy"):
        raise MigrateError(layout.message)
    legacy = layout.legacy_files
    if legacy:
        before = parse_model_files([root / rel for rel in legacy])
        model_text = merged_model([layout.scans[rel] for rel in legacy])
    else:
        model_text = _read_exact(root / model_file())
        before = parse_model_texts([model_text])
    index = _read_index(root)
    entries = _cross_cutting(index)
    has_key = any(RETIRED_ARC42_KEY in e.metadata for e in before.elements)
    if not legacy and not has_key and all(is_flat_doc(e) for e in entries):
        return [message("arch-migrate.nothing")]
    stripped, element_moves = _strip_arc42(model_text, parse_model_texts([model_text]))
    entry_moves = _flattened(entries)
    moves = element_moves + entry_moves
    refusal = _refusal(root, moves, _diagram_keys(index))
    if refusal is not None:
        raise MigrateError(refusal)
    renamed = {m.source for m in entry_moves} | {k for k in _diagram_keys(index) if isinstance(k, str)}
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
    plan = _Plan(outputs=outputs, created=created, moves=moves, renames=renames)
    _verify(root, before, plan, index, {m.source for m in entry_moves})
    return _write(root, plan, legacy)


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
