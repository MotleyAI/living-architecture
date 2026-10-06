"""`la-arch-migrate`: merge the legacy `architecture/model/*.c4` model into `architecture/model.c4`, verified."""

from __future__ import annotations

import contextlib
import sys
import tempfile
from pathlib import Path

from living_architecture.c4.layout import (
    WHITESPACE,
    FileScan,
    classify,
    legacy_model_dir,
    model_file,
    views_file,
)
from living_architecture.c4.model import ModelParse, parse_model, parse_model_files
from living_architecture.c4.views import EMPTY_VIEWS, parse_views
from living_architecture.contract import message

_INDEX_REL = "architecture/index.yaml"


class MigrateError(Exception):
    """The repo cannot be migrated; nothing was written."""


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


def _normalized(model: ModelParse) -> ModelParse:
    """`model` with findings as sorted multisets: merging spec blocks may reorder them."""
    return model.model_copy(update={"findings": sorted(model.findings), "metadata_findings": sorted(model.metadata_findings)})


def _verify(root: Path, legacy: list[Path], outputs: dict[str, str]) -> None:
    """MigrateError unless the staged canonical layout parses exactly like the legacy one."""
    legacy_model = parse_model_files(legacy)
    before = (_normalized(legacy_model), parse_views(root, legacy_model))
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        (staging / "architecture").mkdir()
        index = root / _INDEX_REL
        if index.is_file():
            (staging / _INDEX_REL).write_bytes(index.read_bytes())
        views = root / views_file()
        if views.is_file():
            (staging / views_file()).write_bytes(views.read_bytes())
        for rel, text in outputs.items():
            (staging / rel).write_text(text, encoding="utf-8", newline="")
        staged_model = parse_model(staging)
        after = (_normalized(staged_model), parse_views(staging, staged_model))
    if before != after:
        raise MigrateError(message("arch-migrate.mismatch"))


def _write(root: Path, outputs: dict[str, str], legacy: dict[Path, bytes]) -> list[str]:
    """Create every output, delete the legacy files and an emptied model dir; undo it all on an OSError."""
    created: list[Path] = []
    deleted: list[Path] = []
    model_dir = root / legacy_model_dir()
    removed_dir = False
    try:
        for rel, text in outputs.items():
            path = root / rel
            created.append(path)
            try:
                with path.open("x", encoding="utf-8", newline="") as out:
                    out.write(text)
            except FileExistsError:
                created.pop()
                raise
        for path in legacy:
            path.unlink()
            deleted.append(path)
        if not any(model_dir.iterdir()):
            model_dir.rmdir()
            removed_dir = True
    except OSError:
        if removed_dir:
            with contextlib.suppress(OSError):
                model_dir.mkdir()
        for path in deleted:
            with contextlib.suppress(OSError):
                path.write_bytes(legacy[path])
        for path in created:
            with contextlib.suppress(OSError):
                path.unlink()
        raise
    report = [message("arch-migrate.written", path=rel) for rel in outputs]
    report += [message("arch-migrate.deleted", path=path.relative_to(root).as_posix()) for path in deleted]
    if removed_dir:
        report.append(message("arch-migrate.deleted", path=legacy_model_dir()))
    return report


def migrate(root: Path) -> list[str]:
    """Migrate the repo at `root`; the lines to print. MigrateError or OSError when nothing was written."""
    layout = classify(root)
    if layout.state == "canonical":
        return [message("arch-migrate.nothing")]
    if layout.state != "legacy":
        raise MigrateError(layout.message)
    legacy = {root / rel: (root / rel).read_bytes() for rel in layout.legacy_files}
    outputs = {model_file(): merged_model([layout.scans[rel] for rel in layout.legacy_files])}
    if not layout.views_exists:
        outputs[views_file()] = EMPTY_VIEWS
    _verify(root, list(legacy), outputs)
    return _write(root, outputs, legacy)


def run(root: Path) -> int:
    """`la-arch-migrate`: print each written and deleted path, or exit 2 having changed nothing."""
    try:
        report = migrate(root)
    except (MigrateError, OSError) as exc:
        print(message("arch-migrate.error", error=str(exc)), file=sys.stderr)
        return 2
    for line in report:
        print(line)
    return 0
