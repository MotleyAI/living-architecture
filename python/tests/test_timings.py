"""`dr-refactor --timings`: exclusive phase times from an injected nanosecond clock, printed in the shared order."""

import pytest

from living_architecture.contract import message, timing_phases
from living_architecture.refactor.timings import Timer, seconds

SECOND = 1_000_000_000


class Clock:
    def __init__(self) -> None:
        self.now = 0

    def __call__(self) -> int:
        return self.now


def _line(phase: str, value: str) -> str:
    return message("refactor.timing", phase=phase, seconds=value)


def test_phase_list():
    assert timing_phases() == (
        "load", "resolve", "references", "rules", "blindspot-scan", "literal-scan", "literal-probe", "baseline", "write"
    )


@pytest.mark.parametrize(
    ("ns", "shown"),
    [(1_239_000_000, "1.23"), (4_000_000, "0.00"), (-5, "0.00"), (0, "0.00"), (9_999_999, "0.00"), (10_000_000, "0.01"),
     (123_450_000_001, "123.45")],
)
def test_seconds_floor_to_centiseconds(ns: int, shown: str):
    assert seconds(ns) == shown


def test_nested_phase_is_subtracted_from_its_parent():
    clock = Clock()
    timer = Timer(clock)
    with timer.phase("rules"):
        clock.now += 1 * SECOND
        with timer.phase("blindspot-scan"):
            clock.now += 2 * SECOND
        clock.now += 3 * SECOND
    assert timer.lines() == [_line("rules", "4.00"), _line("blindspot-scan", "2.00"), _line("total", "6.00")]


def test_repeated_runs_add_up():
    clock = Clock()
    timer = Timer(clock)
    for step in (1_000_000_000, 239_000_000):
        with timer.phase("references"):
            clock.now += step
        clock.now += SECOND
    assert timer.lines() == [_line("references", "1.23"), _line("total", "3.23")]


def test_list_order_unrun_phases_omitted_total_last():
    clock = Clock()
    timer = Timer(clock)
    for phase in ("write", "literal-probe", "load"):
        with timer.phase(phase):
            clock.now += 4_000_000
    assert timer.lines() == [
        _line("load", "0.00"), _line("literal-probe", "0.00"), _line("write", "0.00"), _line("total", "0.01")
    ]


def test_no_phase_prints_only_total():
    clock = Clock()
    timer = Timer(clock)
    clock.now += 1_239_000_000
    assert timer.lines() == [_line("total", "1.23")]


def test_a_phase_left_by_an_exception_is_timed():
    clock = Clock()
    timer = Timer(clock)
    with pytest.raises(RuntimeError), timer.phase("baseline"):
        clock.now += SECOND
        raise RuntimeError
    assert timer.lines() == [_line("baseline", "1.00"), _line("total", "1.00")]
