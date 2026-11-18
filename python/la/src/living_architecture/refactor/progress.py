"""`dr-refactor`'s phases and progress lines on stderr, and the refusals a run collects into one report."""

from __future__ import annotations

import sys
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from living_architecture.contract import message


class Refusal(BaseModel):
    """A finding's lines (the finding, then any cause) and its exit code."""

    model_config = ConfigDict(frozen=True)

    lines: tuple[str, ...]
    code: int = 1


def refusal(text: str, code: int = 1) -> Refusal:
    return Refusal(lines=(text,), code=code)


class Refused(Exception):
    """The run refuses with `refusals`, printed in order; the exit code is the highest of theirs and of those
    already `printed`."""

    def __init__(self, refusals: Iterable[Refusal], printed: Iterable[Refusal] = ()) -> None:
        self.refusals = list(refusals)
        self.printed = list(printed)
        super().__init__("\n".join(self.lines))

    @property
    def lines(self) -> list[str]:
        return [line for r in self.refusals for line in r.lines]

    @property
    def code(self) -> int:
        return max((r.code for r in (*self.refusals, *self.printed)), default=1)


def checker_cause(kind: str, error: str, code: int | None, stderr: str) -> list[str]:
    """A failed checker's cause: its exit code and stderr, its start error, or its error answer and stderr."""
    indented = ["  " + line for line in stderr.splitlines()]
    if kind == "exit" and code is not None:
        return [message("refactor.checker-exit", code=code), *indented]
    if kind == "start":
        return [message("refactor.checker-not-started", error=error)]
    if kind == "error":
        return [message("refactor.checker-error", error=error), *indented]
    return []


def unique(refusals: Iterable[Refusal]) -> list[Refusal]:
    """`refusals` in order, each distinct one once."""
    return list(dict.fromkeys(refusals))


def labels(indexes: list[int]) -> str:
    """The map indexes an entry or group stands for."""
    if len(indexes) == 1:
        return message("refactor.progress-entry", index=indexes[0])
    return message("refactor.progress-entries", indexes=", ".join(str(i) for i in indexes))


def entry_refusal(indexes: list[int], locator: str, found: Refusal) -> Refusal:
    """`found` as the refusal of the entry standing for the map `indexes`, located by `locator`."""
    first = message("refactor.entry-refusal", entries=labels(indexes), locator=locator, text=found.lines[0])
    return Refusal(lines=(first, *found.lines[1:]), code=found.code)


class Progress:
    """Writes the phase and progress lines, each flushed as it is printed."""

    def __init__(self) -> None:
        self.phases: list[str] = []

    def _print(self, text: str) -> None:
        print(text, file=sys.stderr, flush=True)

    def phase(self, name: str) -> None:
        self.phases.append(name)
        self._print(message("refactor.progress-phase", phase=name))

    def item(self, n: int, count: int, indexes: list[int], old: str, new: str) -> None:
        """`[references n/count]`: an entry's reference search starts."""
        self._print(message("refactor.progress-item", phase="references", n=n, count=count, entries=labels(indexes),
                            old=old, new=new))

    def result(self, n: int, count: int, indexes: list[int], old: str, new: str, refused: list[str]) -> None:
        """`[rules n/count]`: a group is done, clean or refused with its refusal lines."""
        fields = {"phase": "rules", "n": n, "count": count, "entries": labels(indexes), "old": old, "new": new}
        if not refused:
            self._print(message("refactor.progress-clean", **fields))
            return
        self._print(message("refactor.progress-refused", **fields, refusals=len(refused)))
        for line in refused:
            self._print(line)
