"""`la-arch-migrate`: convert the repo to the current format, merging a legacy model layout and stamping `format`."""

from __future__ import annotations

import contextlib
import os
import secrets
import stat
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel

from living_architecture.c4.layout import (
    WHITESPACE,
    FileScan,
    classify,
    legacy_model_dir,
    model_file,
    sources,
    views_file,
)
from living_architecture.c4.model import ModelParse, parse_model, parse_model_files
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
from living_architecture.contract import config_file, message

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


def _delete(root: Path, rel: str, original: bytes, steps: list[_Step]) -> None:
    path = root / rel
    path.unlink()
    steps.append(
        _Step(rel=rel, undo=lambda: path.write_bytes(original), restored=lambda: path.is_file() and path.read_bytes() == original)
    )


def _remove_dir(root: Path, rel: str, steps: list[_Step]) -> None:
    path = root / rel
    path.rmdir()
    steps.append(_Step(rel=rel, undo=path.mkdir, restored=path.is_dir))


def _replace_config(root: Path, stamped: str, steps: list[_Step]) -> None:
    """Replace the config with `stamped` through a sibling temp file and an atomic rename."""
    config = root / config_file()
    temp = f".{config_file()}.{secrets.token_hex(4)}.tmp"
    _create_exclusive(root, temp, stamped, steps)
    os.chmod(root / temp, stat.S_IMODE(config.stat().st_mode))
    os.replace(root / temp, config)


def _rollback(steps: list[_Step], error: OSError) -> MigrateError | None:
    """Undo `steps` in reverse; an error naming every path that could not be put back, None when all were."""
    for step in reversed(steps):
        with contextlib.suppress(OSError):
            step.undo()
    left = sorted({step.rel for step in steps if not step.restored()})
    if not left:
        return None
    return MigrateError(message("arch-migrate.rollback-failed", error=str(error), paths=", ".join(left)))


def _write(root: Path, outputs: dict[str, str], legacy: dict[str, bytes], stamped: str) -> list[str]:
    """Create every output, delete the legacy files and an emptied model dir, replace the config last; all or nothing."""
    steps: list[_Step] = []
    deleted: list[str] = []
    model_dir = legacy_model_dir()
    try:
        for rel, text in outputs.items():
            _create_exclusive(root, rel, text, steps)
        for rel, original in legacy.items():
            _delete(root, rel, original, steps)
            deleted.append(rel)
        if legacy and not any((root / model_dir).iterdir()):
            _remove_dir(root, model_dir, steps)
            deleted.append(model_dir)
        _replace_config(root, stamped, steps)
    except OSError as exc:
        failure = _rollback(steps, exc)
        if failure is None:
            raise
        raise failure from exc
    written = [*outputs, config_file()]
    return [message("arch-migrate.written", path=rel) for rel in written] + [
        message("arch-migrate.deleted", path=rel) for rel in deleted
    ]


def _layout(root: Path) -> tuple[dict[str, str], dict[str, bytes]]:
    """The canonical files to write and the legacy files to delete; none when there is no layout to convert."""
    if not os.path.lexists(root / _INDEX_REL) and not sources(root):
        return {}, {}
    layout = classify(root)
    if layout.state == "canonical":
        return {}, {}
    if layout.state != "legacy":
        raise MigrateError(layout.message)
    legacy = {rel: (root / rel).read_bytes() for rel in layout.legacy_files}
    outputs = {model_file(): merged_model([layout.scans[rel] for rel in layout.legacy_files])}
    if not layout.views_exists:
        outputs[views_file()] = EMPTY_VIEWS
    _verify(root, [root / rel for rel in legacy], outputs)
    return outputs, legacy


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
    outputs, legacy = _layout(root)
    return _write(root, outputs, legacy, stamped)


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
