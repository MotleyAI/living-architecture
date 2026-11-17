"""`PATH[:LINE]` sites of `rename --keep`, `--with` and `--without`."""

from __future__ import annotations

import ast
import os
import re
import tokenize
from collections.abc import Callable, Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from living_architecture.contract import message
from living_architecture.refactor.progress import Refusal, refusal
from living_architecture.refactor.python_source import nfkc, split_lines

_LINE = re.compile(r"(.*):(\d+)")
_TYPE_COMMENT = re.compile(r"#\s*type:")


class Site(BaseModel):
    """A site as given, its real path relative to the project (None outside it) and its line."""

    model_config = ConfigDict(frozen=True)

    raw: str
    parts: tuple[str, ...] | None
    line: int | None

    @classmethod
    def parse(cls, raw: str, root: Path, base: Path | None = None) -> Site:
        """`raw` with its path resolved against `base` (default: the working directory)."""
        m = _LINE.fullmatch(raw)
        path, line = (m.group(1), int(m.group(2))) if m else (raw, None)
        real = Path(os.path.realpath((base or Path.cwd()) / path))
        parts = real.relative_to(root).parts if real.is_relative_to(root) and real.exists() else None
        return cls(raw=raw, parts=parts, line=line)

    def covers(self, rel: str, line: int) -> bool:
        """`rel:line` is this site: the same line of the file, or anywhere in the file or under the directory."""
        return self.covers_path(rel) and (self.line is None or self.line == line)

    def covers_path(self, rel: str) -> bool:
        """`rel` is this site's file or under its directory."""
        if self.parts is None:
            return False
        return tuple(Path(rel).parts)[: len(self.parts)] == self.parts

    def missing(self, root: Path) -> bool:
        """The site names no file or directory under `root`, or a line its file does not have."""
        if self.parts is None or self.line is None:
            return self.parts is None
        path = root.joinpath(*self.parts)
        if not path.is_file():
            return True
        try:
            count = len(split_lines(path.read_bytes().decode("utf-8", errors="replace")))
        except OSError:
            return True
        return not 1 <= self.line <= count


class Keeps:
    """`--keep` sites: what they keep, and the first that kept nothing."""

    def __init__(self, raws: tuple[str, ...], root: Path, base: Path | None = None) -> None:
        self.sites = [Site.parse(raw, root, base) for raw in raws]
        self._matched: set[int] = set()

    def kept(self, rel: str, line: int | None, *, mark: bool = True) -> bool:
        """`rel:line` is kept (`line` None: the whole file, as a move); `mark` counts the keeps it matches."""
        hits = {i for i, s in enumerate(self.sites) if (line is not None or s.line is None) and s.covers(rel, line or 0)}
        if mark:
            self._matched |= hits
        return bool(hits)

    def unmatched(self) -> list[str]:
        """Every keep that matched nothing, in command-line order."""
        return [s.raw for s in self.unmatched_sites()]

    def unmatched_sites(self) -> list[Site]:
        return [s for i, s in enumerate(self.sites) if i not in self._matched]


def nearest_line(edited: Iterable[int], line: int) -> int | None:
    """The line of `edited` nearest to `line`, the earlier of two equally near; None when there is none."""
    return min(edited, key=lambda e: (abs(e - line), e), default=None)


def resolve_keeps(keeps: Keeps, edits: Iterable[tuple[str, int]]) -> tuple[list[str], list[Refusal]]:
    """Each keep that matched nothing: a `refactor.keep-unneeded` warning for a whole-path keep, a refusal naming the
    nearest of its file's edited lines (`edits`: path and start line) for a line keep."""
    edited: dict[str, list[int]] = {}
    for rel, line in edits:
        edited.setdefault(rel, []).append(line)
    warnings: list[str] = []
    refusals: list[Refusal] = []
    for site in keeps.unmatched_sites():
        if site.line is None:
            warnings.append(message("refactor.keep-unneeded", site=site.raw))
            continue
        rel = "/".join(site.parts or ())
        near = nearest_line(edited.get(rel, ()), site.line)
        text = (message("refactor.keep-unmatched", site=site.raw) if near is None
                else message("refactor.keep-unmatched-near", site=site.raw, path=rel, line=near))
        refusals.append(refusal(text, 2))
    return warnings, refusals


def _uncommented(text: str) -> list[str] | None:
    """`text`'s lines with every comment but a type comment blanked; None when it does not tokenize."""
    lines = split_lines(text)
    try:
        tokens = list(tokenize.generate_tokens(iter(list(lines)).__next__))
    except (tokenize.TokenError, SyntaxError):
        return None
    for token in tokens:
        if token.type != tokenize.COMMENT or _TYPE_COMMENT.match(token.string):
            continue
        row, start = token.start
        line = lines[row - 1]
        lines[row - 1] = line[:start] + " " * (token.end[1] - start) + line[token.end[1]:]
    return lines


def spelled_lines(text: str, names: Iterable[str], *, code: bool = True, comments: bool = True) -> set[int]:
    """The 1-based lines of `text` spelling one of `names` as written (NFKC-normalized) or, in `code`, in the value of
    a string literal starting on the line; without `comments`, a code comment's spelling counts only in a type
    comment."""
    wanted = {nfkc(n) for n in names}
    lines = (None if comments or not code else _uncommented(text)) or split_lines(text)
    out = {i for i, line in enumerate(lines, 1) if any(n in nfkc(line) for n in wanted)}
    if not code:
        return out
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and any(n in node.value for n in wanted):
            out.add(node.lineno)
    return out


def keep_spells(site: Site, editable: dict[str, bool], text: Callable[[str], str], names: set[str],
                moved: list[str], *, docs: bool) -> bool:
    """`site` covers a file the refactor moves, or a line of an `editable` file (its value: a source, else prose)
    spelling one of `names` (in a comment only with `docs`)."""
    if site.parts is not None and any(
        site.covers_path(rel) or site.parts[: len(Path(rel).parts)] == Path(rel).parts for rel in moved
    ):
        return True
    for rel, is_code in editable.items():
        if not site.covers_path(rel):
            continue
        try:
            lines = spelled_lines(text(rel), names, code=is_code, comments=docs)
        except (OSError, UnicodeDecodeError, LookupError):
            continue
        if lines and (site.line is None or site.line in lines):
            return True
    return False
