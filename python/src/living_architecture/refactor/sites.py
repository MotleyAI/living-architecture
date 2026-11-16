"""`PATH[:LINE]` sites of `rename --keep`, `--with` and `--without`."""

from __future__ import annotations

import ast
import os
import re
from collections.abc import Callable, Iterable
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from living_architecture.refactor.python_source import nfkc, split_lines

_LINE = re.compile(r"(.*):(\d+)")


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
        return [s.raw for i, s in enumerate(self.sites) if i not in self._matched]


class SiteError(Exception):
    """A site that matches nothing it must; `template` is its finding."""

    def __init__(self, template: str, site: str) -> None:
        super().__init__(site)
        self.template = template
        self.site = site


def spelled_lines(text: str, names: Iterable[str], *, code: bool = True) -> set[int]:
    """The 1-based lines of `text` spelling one of `names` as written (NFKC-normalized) or, in `code`, in the value of
    a string literal starting on the line."""
    wanted = {nfkc(n) for n in names}
    out = {i for i, line in enumerate(split_lines(text), 1) if any(n in nfkc(line) for n in wanted)}
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
                moved: list[str]) -> bool:
    """`site` covers a file the refactor moves, or a line of an `editable` file (its value: a source, else prose)
    spelling one of `names`."""
    if site.parts is not None and any(
        site.covers_path(rel) or site.parts[: len(Path(rel).parts)] == Path(rel).parts for rel in moved
    ):
        return True
    for rel, is_code in editable.items():
        if not site.covers_path(rel):
            continue
        try:
            lines = spelled_lines(text(rel), names, code=is_code)
        except (OSError, UnicodeDecodeError, LookupError):
            continue
        if lines and (site.line is None or site.line in lines):
            return True
    return False
