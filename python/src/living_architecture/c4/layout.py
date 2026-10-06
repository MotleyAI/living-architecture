"""The canonical LikeC4 layout: exactly `architecture/model.c4` and `architecture/views.c4`, each with its blocks."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from living_architecture.c4.model import strip_line_comment
from living_architecture.contract import architecture, message

_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
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


def _skip_trivia(text: str, pos: int) -> int:
    """Past whitespace and `//` comments."""
    while pos < len(text):
        if text[pos] in WHITESPACE:
            pos += 1
        elif text.startswith("//", pos):
            end = text.find("\n", pos)
            pos = len(text) if end < 0 else end
        else:
            break
    return pos


def _balanced_end(text: str, pos: int, depth: int, *, stop_at_eol: bool) -> tuple[int, int]:
    """Walk from `pos` at brace `depth` (quote- and comment-aware) to where depth returns to 0.

    `stop_at_eol`: also stop at a newline or an unmatched `}` reached at depth 0. Returns (offset, final depth).
    """
    in_q = False
    while pos < len(text):
        ch = text[pos]
        if ch == "\n":
            in_q = False
            if stop_at_eol and depth == 0:
                return pos, 0
        elif in_q:
            in_q = ch != "'"
        elif ch == "'":
            in_q = True
        elif text.startswith("//", pos):
            end = text.find("\n", pos)
            pos = len(text) if end < 0 else end
            continue
        elif ch == "{":
            depth += 1
        elif ch == "}":
            if depth == 0:
                return pos, 0
            depth -= 1
            if depth == 0 and not stop_at_eol:
                return pos, 0
        pos += 1
    return pos, depth


def scan(text: str) -> FileScan:
    """Split `text` into top-level blocks; anything else but whitespace and comments is a problem."""
    blocks: list[Block] = []
    problems: list[_Problem] = []
    pos = _skip_trivia(text, 0)
    while pos < len(text):
        word = _WORD_RE.match(text, pos)
        brace = _skip_trivia(text, word.end()) if word else pos
        if word and brace < len(text) and text[brace] == "{":
            close, depth = _balanced_end(text, brace + 1, 1, stop_at_eol=False)
            closed = depth == 0 and close < len(text)
            blocks.append(
                Block(kind=word.group(), line=_line(text, pos), start=pos, open=brace, close=close if closed else None)
            )
            if not closed:
                problems.append(_Problem(offset=pos, line=_line(text, pos), id="c4-layout.unbalanced-braces"))
                break
            pos = _skip_trivia(text, close + 1)
            continue
        if text[pos] == "}":
            problems.append(_Problem(offset=pos, line=_line(text, pos), id="c4-layout.unbalanced-braces"))
            pos = _skip_trivia(text, pos + 1)
            continue
        end, depth = _balanced_end(text, pos, 0, stop_at_eol=True)
        shown = strip_line_comment(text[pos:end].split("\n")[0]).strip(WHITESPACE)
        problems.append(_Problem(offset=pos, line=_line(text, pos), id="c4-layout.top-level-text", text=shown))
        if depth:
            problems.append(_Problem(offset=pos, line=_line(text, pos), id="c4-layout.unbalanced-braces"))
        pos = _skip_trivia(text, end)
    return FileScan(text=text, blocks=blocks, problems=problems)


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


def _read(root: Path, rel: str) -> FileScan:
    return scan((root / rel).read_bytes().decode("utf-8"))


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


def _canonical_state(root: Path, rel: str) -> Literal["file", "missing", "not-a-file"]:
    path = root / rel
    if path.is_file():
        return "file"
    return "not-a-file" if os.path.lexists(path) else "missing"


def _is_legacy_file(rel: str, file_scan: FileScan) -> bool:
    directly_in_model_dir = rel.rsplit("/", 1)[0] == legacy_model_dir() and rel.endswith(".c4")
    allowed = architecture()["blocks"][model_file()]
    return directly_in_model_dir and not file_scan.problems and all(b.kind in allowed for b in file_scan.blocks)


def classify(root: Path) -> Layout:
    """Discover, scan and classify every LikeC4 source under `architecture/`."""
    canonical = [model_file(), views_file()]
    states = {rel: _canonical_state(root, rel) for rel in canonical}
    strays = [rel for rel in sources(root) if rel not in canonical]
    scans = {rel: _read(root, rel) for rel in [*strays, *(r for r in canonical if states[r] == "file")]}
    violations: dict[str, list[str]] = {}
    for rel in canonical:
        if states[rel] == "file":
            violations[rel] = _block_violations(rel, scans[rel])
        else:
            violations[rel] = [message(f"c4-layout.{states[rel]}", path=rel)]
    for rel in strays:
        violations[rel] = _stray_violations(rel, scans[rel])
    lines = [line for rel in sorted(violations) for line in violations[rel]]
    views_exists = states[views_file()] == "file"
    if not lines:
        return Layout(state="canonical", message=None, legacy_files=[], scans=scans, views_exists=views_exists)
    legacy = (
        bool(strays)
        and states[model_file()] == "missing"
        and all(_is_legacy_file(rel, scans[rel]) for rel in strays)
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
