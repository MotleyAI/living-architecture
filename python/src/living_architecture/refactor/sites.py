"""`PATH[:LINE]` sites of `rename --keep`, `--with` and `--without`."""

from __future__ import annotations

import os
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

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
        if self.parts is None:
            return False
        path = tuple(Path(rel).parts)
        return path[: len(self.parts)] == self.parts and (self.line is None or self.line == line)


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

    def check(self) -> None:
        """`SiteError` for the first keep that matched nothing."""
        unmatched = next((s for i, s in enumerate(self.sites) if i not in self._matched), None)
        if unmatched is not None:
            raise SiteError("refactor.keep-unmatched", unmatched.raw)


class SiteError(Exception):
    """A site that matches nothing it must; `template` is its finding."""

    def __init__(self, template: str, site: str) -> None:
        super().__init__(site)
        self.template = template
        self.site = site
