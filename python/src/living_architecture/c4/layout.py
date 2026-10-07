"""The canonical LikeC4 layout: exactly `architecture/model.c4` and `architecture/views.c4`, each with its blocks."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from living_architecture.c4.model import strip_line_comment
from living_architecture.contract import architecture, message

_WORD_RE = re.compile(r"\w+", re.ASCII)
_UNBALANCED = "c4-layout.unbalanced-braces"
WHITESPACE = " \t\n\r\f\v"


class Block(BaseModel):
    """A top-level `<kind> { }` block; `close` is the offset of its `}`, None when unclosed."""

    kind: str
    line: int
    start: int
    open: int
    close: int | None


class _Problem(BaseModel):
    offset: int
    line: int
    id: str
    text: str = ""


class FileScan(BaseModel):
    """One LikeC4 source: its text, top-level blocks and lexical problems, in file order."""

    text: str
    blocks: list[Block]
    problems: list[_Problem]


class Layout(BaseModel):
    """The classified layout of `architecture/`; `message` is None exactly when it is canonical."""

    state: Literal["canonical", "legacy", "other"]
    message: str | None
    legacy_files: list[str]
    scans: dict[str, FileScan]
    views_exists: bool


def model_file() -> str:
    return architecture()["model_file"]


def views_file() -> str:
    return architecture()["views_file"]


def legacy_model_dir() -> str:
    return architecture()["legacy_model_dir"]


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _line_end(text: str, pos: int) -> int:
    end = text.find("\n", pos)
    return len(text) if end < 0 else end


def _skip_trivia(text: str, pos: int) -> int:
    """Past whitespace and `//` comments."""
    while pos < len(text):
        if text[pos] in WHITESPACE:
            pos += 1
        elif text.startswith("//", pos):
            pos = _line_end(text, pos)
        else:
            break
    return pos


def _skip_opaque(text: str, pos: int) -> int | None:
    """Past a `'` string (closed by `'` or the end of line) or a `//` comment at `pos`; None at anything else."""
    if text[pos] == "'":
        eol = _line_end(text, pos + 1)
        close = text.find("'", pos + 1, eol)
        return eol if close < 0 else close + 1
    if text.startswith("//", pos):
        return _line_end(text, pos)
    return None


def _balanced_end(text: str, pos: int, depth: int, *, stop_at_eol: bool) -> tuple[int, int]:
    """Walk from `pos` at brace `depth` (quote- and comment-aware) to where depth returns to 0.

    `stop_at_eol`: also stop at a newline or an unmatched `}` reached at depth 0. Returns (offset, final depth).
    """
    while pos < len(text):
        skipped = _skip_opaque(text, pos)
        if skipped is not None:
            pos = skipped
            continue
        ch = text[pos]
        if ch == "\n" and stop_at_eol and depth == 0:
            return pos, 0
        if ch == "{":
            depth += 1
        elif ch == "}":
            if depth == 0 or (depth == 1 and not stop_at_eol):
                return pos, 0
            depth -= 1
        pos += 1
    return pos, depth


def _add_problem(file_scan: FileScan, offset: int, problem_id: str, shown: str = "") -> None:
    file_scan.problems.append(_Problem(offset=offset, line=_line(file_scan.text, offset), id=problem_id, text=shown))


def _scan_item(file_scan: FileScan, pos: int) -> int | None:
    """Scan the top-level block, stray `}` or text line at `pos`; the next position, None after an unclosed block."""
    text = file_scan.text
    word = _WORD_RE.match(text, pos)
    brace = _skip_trivia(text, word.end()) if word else pos
    if word and brace < len(text) and text[brace] == "{":
        close, depth = _balanced_end(text, brace + 1, 1, stop_at_eol=False)
        closed = depth == 0 and close < len(text)
        file_scan.blocks.append(
            Block(kind=word.group(), line=_line(text, pos), start=pos, open=brace, close=close if closed else None)
        )
        if not closed:
            _add_problem(file_scan, pos, _UNBALANCED)
            return None
        return _skip_trivia(text, close + 1)
    if text[pos] == "}":
        _add_problem(file_scan, pos, _UNBALANCED)
        return _skip_trivia(text, pos + 1)
    end, depth = _balanced_end(text, pos, 0, stop_at_eol=True)
    shown = strip_line_comment(text[pos:end].split("\n")[0]).strip(WHITESPACE)
    _add_problem(file_scan, pos, "c4-layout.top-level-text", shown)
    if depth:
        _add_problem(file_scan, pos, _UNBALANCED)
    return _skip_trivia(text, end)


def scan(text: str) -> FileScan:
    """Split `text` into top-level blocks; anything else but whitespace and comments is a problem."""
    file_scan = FileScan(text=text, blocks=[], problems=[])
    pos: int | None = _skip_trivia(text, 0)
    while pos is not None and pos < len(text):
        pos = _scan_item(file_scan, pos)
    return file_scan


def _walk_error(error: OSError) -> None:
    raise error


def sources(root: Path) -> list[str]:
    """Every LikeC4 source file under `architecture/`, repo-relative, in code-point order."""
    arch = root / "architecture"
    if not arch.is_dir():
        return []
    extensions = tuple(architecture()["source_extensions"])
    found: list[str] = []
    for here, _dirs, names in os.walk(arch, onerror=_walk_error):
        for name in names:
            path = Path(here) / name
            if name.endswith(extensions) and path.is_file():
                found.append(path.relative_to(root).as_posix())
    return sorted(found)


def _read(root: Path, rel: str) -> FileScan | None:
    """The scan of `rel`, or None when it is not valid UTF-8."""
    try:
        text = (root / rel).read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return None
    return scan(text)


def _render(rel: str, problem: _Problem) -> str:
    return message(problem.id, path=rel, line=problem.line, text=problem.text)


def _block_violations(rel: str, file_scan: FileScan) -> list[str]:
    """The block rules of one canonical file, in file order; missing blocks last."""
    allowed: list[str] = architecture()["blocks"][rel]
    found: list[tuple[int, str]] = [(p.offset, _render(rel, p)) for p in file_scan.problems]
    seen: set[str] = set()
    for block in file_scan.blocks:
        if block.kind not in allowed:
            found.append((block.start, message("c4-layout.block-not-allowed", path=rel, line=block.line, block=block.kind)))
        elif block.kind in seen:
            found.append((block.start, message("c4-layout.block-duplicate", path=rel, line=block.line, block=block.kind)))
        seen.add(block.kind)
    lines = [text for _, text in sorted(found, key=lambda item: item[0])]
    return lines + [message("c4-layout.block-missing", path=rel, block=kind) for kind in allowed if kind not in seen]


def _stray_violations(rel: str, file_scan: FileScan) -> list[str]:
    kinds = list(dict.fromkeys(block.kind for block in file_scan.blocks))
    holding = ", ".join(f"`{kind}`" for kind in kinds) if kinds else message("c4-layout.no-blocks")
    return [message("c4-layout.stray", path=rel, blocks=holding)] + [_render(rel, p) for p in file_scan.problems]


_CanonicalState = Literal["file", "missing", "not-a-file"]


def _canonical_state(root: Path, rel: str) -> _CanonicalState:
    path = root / rel
    if path.is_file():
        return "file"
    return "not-a-file" if os.path.lexists(path) else "missing"


def _is_legacy_file(rel: str, file_scan: FileScan | None) -> bool:
    if file_scan is None:
        return False
    directly_in_model_dir = rel.rsplit("/", 1)[0] == legacy_model_dir() and rel.endswith(".c4")
    allowed = architecture()["blocks"][model_file()]
    return directly_in_model_dir and not file_scan.problems and all(b.kind in allowed for b in file_scan.blocks)


def _file_violations(root: Path, rel: str, state: _CanonicalState | None, scans: dict[str, FileScan]) -> list[str]:
    """The violations of one file (`state` None for a stray); records its scan in `scans` when it decodes."""
    if state is not None and state != "file":
        return [message(f"c4-layout.{state}", path=rel)]
    file_scan = _read(root, rel)
    if file_scan is None:
        return [message("c4-layout.not-utf8", path=rel)]
    scans[rel] = file_scan
    return _stray_violations(rel, file_scan) if state is None else _block_violations(rel, file_scan)


def classify(root: Path) -> Layout:
    """Discover, scan and classify every LikeC4 source under `architecture/`."""
    canonical = [model_file(), views_file()]
    states: dict[str, _CanonicalState] = {rel: _canonical_state(root, rel) for rel in canonical}
    strays = [rel for rel in sources(root) if rel not in canonical]
    scans: dict[str, FileScan] = {}
    violations = {rel: _file_violations(root, rel, states.get(rel), scans) for rel in [*canonical, *strays]}
    lines = [line for rel in sorted(violations) for line in violations[rel]]
    views_exists = states[views_file()] == "file"
    if not lines:
        return Layout(state="canonical", message=None, legacy_files=[], scans=scans, views_exists=views_exists)
    legacy = (
        bool(strays)
        and states[model_file()] == "missing"
        and all(_is_legacy_file(rel, scans.get(rel)) for rel in strays)
        and (states[views_file()] == "missing" or (views_exists and not violations[views_file()]))
    )
    tail = message("c4-layout.migrate" if legacy else "c4-layout.merge-by-hand")
    text = "\n".join([message("c4-layout.header"), *lines, tail])
    return Layout(
        state="legacy" if legacy else "other",
        message=text,
        legacy_files=strays if legacy else [],
        scans=scans,
        views_exists=views_exists,
    )


def layout_problem(root: Path) -> str | None:
    """The layout message naming every violation, or None when the layout is canonical."""
    return classify(root).message
