"""`dr-refactor --timings`: each phase's exclusive wall time, printed in the shared phase order."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager

from living_architecture.contract import message, timing_phases

_CENTISECOND_NS = 10_000_000


def seconds(ns: int) -> str:
    """`ns` floored to whole centiseconds, never negative, as `S.CC`."""
    cs = max(ns, 0) // _CENTISECOND_NS
    return f"{cs // 100}.{cs % 100:02d}"


class Timer:
    """A stack of phases: entering one pauses the one below it, leaving it resumes that one."""

    def __init__(self, clock: Callable[[], int] = time.monotonic_ns) -> None:
        self._clock = clock
        self._start = clock()
        self._spent: dict[str, int] = {}
        self._stack: list[str] = []
        self._since = self._start

    def _charge(self) -> None:
        now = self._clock()
        if self._stack:
            top = self._stack[-1]
            self._spent[top] = self._spent.get(top, 0) + now - self._since
        self._since = now

    @contextmanager
    def phase(self, name: str) -> Generator[None]:
        self._charge()
        self._stack.append(name)
        self._spent.setdefault(name, 0)
        try:
            yield
        finally:
            self._charge()
            self._stack.pop()

    def lines(self) -> list[str]:
        """One `refactor.timing` line per phase that ran, in list order, then `total`."""
        ran = [(p, self._spent[p]) for p in timing_phases() if p in self._spent]
        ran.append(("total", self._clock() - self._start))
        return [message("refactor.timing", phase=p, seconds=seconds(ns)) for p, ns in ran]


_active: list[Timer] = []


@contextmanager
def timed(name: str) -> Generator[None]:
    """Time `name` on the active timer; a no-op without one."""
    if not _active:
        yield
        return
    with _active[-1].phase(name):
        yield


class Report:
    """The scope of a `--timings` run; `cancel` when another twin's run prints its own lines."""

    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


@contextmanager
def report(enabled: bool) -> Generator[Report]:
    """With `enabled`, time the scope and print its lines on stderr after all other output, however it exits."""
    scope = Report()
    if not enabled:
        yield scope
        return
    timer = Timer()
    _active.append(timer)
    try:
        yield scope
    finally:
        _active.remove(timer)
        if not scope.cancelled:
            sys.stdout.flush()
            print("\n".join(timer.lines()), file=sys.stderr)
            sys.stderr.flush()
