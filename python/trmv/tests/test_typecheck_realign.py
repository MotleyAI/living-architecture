"""`la-typecheck --realign-from`: the backward mapping, entry taking in list order, and renamed baseline keys."""

from trmv.lang.baseline import Key
from trmv.lang.realign import Entries, back_key, merged, realigned, rekeyed

ARG = "reportArgumentType"
ASSIGN = "reportAssignmentType"


def _entry(code: str, start: int, end: int, lines: int = 1) -> dict[str, object]:
    return {"code": code, "range": {"startColumn": start, "endColumn": end, "lineCount": lines}}


def _key(code: str, line: int, start: int, end: int, lines: int = 1) -> Key:
    return (code, line, start, line + lines - 1, end)


def _in_order(matched: list[Key], unmatched: list[Key]) -> list[tuple[Key, bool]]:
    return sorted([*((key, True) for key in matched), *((key, False) for key in unmatched)], key=lambda d: d[0][1:3])


def _realigned(entries: Entries, matched: list[Key], unmatched: list[Key], current: str, at_ref: str) -> Entries:
    return realigned(entries, _in_order(matched, unmatched), current, at_ref)


def _merged(held: Entries, moved: Entries, matched: list[Key], unmatched: list[Key], current: str, at_ref: str) -> Entries:
    return merged(held, moved, _in_order(matched, unmatched), current, at_ref)


AT_REF = """\
def f(a: int, b: int) -> int:
    return a + b


def use() -> int:
    return f(1, "x") + len(3)
"""
EDITED = AT_REF.replace("f(1,", "f(int(1),")


def test_a_range_after_the_edit_maps_back_to_its_columns_at_ref() -> None:
    assert back_key(EDITED, AT_REF, _key(ARG, 5, 21, 24)) == _key(ARG, 5, 16, 19)
    assert back_key(EDITED, AT_REF, _key(ARG, 5, 32, 33)) == _key(ARG, 5, 27, 28)


def test_a_range_on_an_untouched_line_maps_back_to_its_line_at_ref() -> None:
    current = "import os\n\n\n" + AT_REF
    assert back_key(current, AT_REF, _key(ARG, 8, 16, 19)) == _key(ARG, 5, 16, 19)


def test_a_range_in_added_text_maps_back_to_nothing() -> None:
    current = AT_REF + "\n\ndef more() -> None:\n    print(len(4))\n"
    assert back_key(current, AT_REF, _key(ARG, 9, 14, 15)) is None


def test_shifted_entries_get_the_current_columns() -> None:
    entries = [_entry(ARG, 16, 19), _entry(ARG, 27, 28)]
    unmatched = [_key(ARG, 5, 21, 24), _key(ARG, 5, 32, 33)]
    assert _realigned(entries, [], unmatched, EDITED, AT_REF) == [_entry(ARG, 21, 24), _entry(ARG, 32, 33)]
    assert entries == [_entry(ARG, 16, 19), _entry(ARG, 27, 28)]


def test_a_matched_entry_and_an_entry_without_a_diagnostic_are_kept() -> None:
    entries = [_entry(ARG, 16, 19), _entry(ARG, 27, 28)]
    current = AT_REF.replace("+ len(3)", "+ int(len(3))")
    assert _realigned(entries, [_key(ARG, 5, 16, 19)], [_key(ARG, 5, 31, 32)], current, AT_REF) == [
        _entry(ARG, 16, 19), _entry(ARG, 31, 32)]
    stale = [_entry("reportCallIssue", 4, 9), *entries]
    assert _realigned(stale, [], [_key(ARG, 5, 21, 24), _key(ARG, 5, 32, 33)], EDITED, AT_REF) == [
        stale[0], _entry(ARG, 21, 24), _entry(ARG, 32, 33)]


def test_another_rule_or_other_columns_at_ref_take_no_entry() -> None:
    entries = [_entry(ARG, 16, 19), _entry(ARG, 27, 28)]
    assert _realigned(entries, [], [_key("reportCallIssue", 5, 21, 24)], EDITED, AT_REF) == entries
    assert _realigned(entries, [], [_key(ARG, 5, 21, 25)], EDITED, AT_REF) == entries


def test_an_error_in_added_text_takes_no_entry() -> None:
    at_ref = AT_REF + "\n\ndef other() -> int:\n    return 1\n"
    current = at_ref.replace("+ len(3)", "+ 3") + "\n\ndef more() -> None:\n    print(len(4))\n"
    entries = [_entry(ARG, 16, 19), _entry(ARG, 27, 28)]
    assert _realigned(entries, [_key(ARG, 5, 16, 19)], [_key(ARG, 13, 14, 15)], current, at_ref) == entries


SAME_SHAPE = """\
def use(v: str) -> int:
    a = len(3)
    b = len(4)
    c = len(v)
    return a + b + c
"""


def test_identical_entries_are_each_taken_once_in_order() -> None:
    current = (SAME_SHAPE.replace("v: str", "v: int").replace("a = len", "a = 0 + len")
               .replace("b = len", "b = 100 + len").replace("c = len", "c = 10000 + len"))
    unmatched = [_key(ARG, 1, 16, 17), _key(ARG, 2, 18, 19), _key(ARG, 3, 20, 21)]
    entries = [_entry(ARG, 12, 13), _entry(ARG, 12, 13)]
    assert _realigned(entries, [], unmatched, current, SAME_SHAPE) == [_entry(ARG, 16, 17), _entry(ARG, 18, 19)]


def test_a_shifted_error_before_a_still_matched_one_of_the_same_shape_takes_the_first_entry() -> None:
    current = SAME_SHAPE.replace("a = len", "a = 0 + len")
    entries = [_entry(ARG, 12, 13), _entry(ARG, 12, 13)]
    assert _realigned(entries, [_key(ARG, 2, 12, 13)], [_key(ARG, 1, 16, 17)], current, SAME_SHAPE) == [
        _entry(ARG, 16, 17), _entry(ARG, 12, 13)]


def test_a_shifted_error_after_a_still_matched_one_of_the_same_shape_takes_the_second_entry() -> None:
    current = SAME_SHAPE.replace("b = len", "b = 0 + len")
    entries = [_entry(ARG, 12, 13), _entry(ARG, 12, 13)]
    assert _realigned(entries, [_key(ARG, 1, 12, 13)], [_key(ARG, 2, 16, 17)], current, SAME_SHAPE) == [
        _entry(ARG, 12, 13), _entry(ARG, 16, 17)]


def test_a_long_run_of_matched_entries_before_a_shifted_one_is_paired_in_order() -> None:
    lines = "".join(f"    x{i} = len({i})\n" for i in range(3000))
    at_ref = f"def use() -> None:\n{lines}    y = len(3)\n"
    current = at_ref.replace("y = len", "y = 0 + len")
    entries = [_entry(ARG, 8 + len(str(i)), 9 + 2 * len(str(i))) for i in range(3000)] + [_entry(ARG, 12, 13)]
    matched = [_key(ARG, i + 1, 8 + len(str(i)), 9 + 2 * len(str(i))) for i in range(3000)]
    out = _realigned(entries, matched, [_key(ARG, 3001, 16, 17)], current, at_ref)
    assert out == [*entries[:-1], _entry(ARG, 16, 17)]


def test_a_shifted_error_between_long_runs_of_matched_entries_is_paired_in_order() -> None:
    def run(start: int) -> str:
        return "".join(f"    x{i} = len({i})\n" for i in range(start, start + 2000))

    at_ref = f"def use() -> None:\n{run(1000)}    y = len(3)\n{run(3000)}"
    current = at_ref.replace("y = len", "y = 0 + len")
    side = [_entry(ARG, 15, 19)] * 2000
    matched = [_key(ARG, line, 15, 19) for line in [*range(1, 2001), *range(2002, 4002)]]
    out = _realigned([*side, _entry(ARG, 12, 13), *side], matched, [_key(ARG, 2001, 16, 17)], current, at_ref)
    assert out == [*side, _entry(ARG, 16, 17), *side]


def test_diagnostics_at_one_start_keep_the_checkers_order() -> None:
    current = EDITED.replace("f(int(1),", "f(int(int(1)),")
    entries = [_entry(ARG, 21, 24), _entry("reportCallIssue", 21, 30)]
    report = [(_key("reportCallIssue", 5, 26, 35), False), (_key(ARG, 5, 26, 29), False)]
    assert realigned(entries, report, current, EDITED) == [_entry(ARG, 21, 24), _entry("reportCallIssue", 26, 35)]
    assert realigned(entries, report[::-1], current, EDITED) == [_entry(ARG, 26, 29), _entry("reportCallIssue", 26, 35)]


OUT_OF_ORDER = """\
def f(a: int, b: int) -> int:
    return a + b


def use(v: str) -> int:
    a = len(3)
    b = f(1, "x")
    c = len(v)
    return a + b + c
"""


def test_an_entry_before_a_matched_one_is_not_taken_by_a_later_error() -> None:
    current = OUT_OF_ORDER.replace("v: str", "v: int").replace("len(3)", 'len("")').replace("c = len", "c = 0 + len")
    entries = [_entry(ARG, 12, 13), _entry(ARG, 13, 16)]
    assert back_key(current, OUT_OF_ORDER, _key(ARG, 7, 16, 17)) == _key(ARG, 7, 12, 13)
    assert _realigned(entries, [_key(ARG, 6, 13, 16)], [_key(ARG, 7, 16, 17)], current, OUT_OF_ORDER) == entries


def test_an_entry_after_a_matched_one_is_not_taken_by_an_earlier_error() -> None:
    at_ref = OUT_OF_ORDER.replace("    a = len(3)\n", "    a = len(v)\n").replace("    c = len(v)\n", "    c = len(3)\n")
    current = at_ref.replace("v: str", "v: int").replace("a = len", "a = 0 + len").replace("len(3)", 'len("")')
    entries = [_entry(ARG, 13, 16), _entry(ARG, 12, 13)]
    assert _realigned(entries, [_key(ARG, 6, 13, 16)], [_key(ARG, 5, 16, 17)], current, at_ref) == entries


MULTI_LINE = """\
def get() -> int:
    return 1


def use() -> None:
    y: str = (
        get())
    print(y)
"""


def test_a_multi_line_entry_keeps_its_line_count() -> None:
    current = MULTI_LINE.replace("    y: str", "    value: str").replace("print(y)", "print(value)")
    unmatched = [_key(ASSIGN, 5, 17, 14, lines=2)]
    assert _realigned([_entry(ASSIGN, 13, 14, 2)], [], unmatched, current, MULTI_LINE) == [_entry(ASSIGN, 17, 14, 2)]


EMOJI = """\
def g(s: str, n: int) -> int:
    return n


def use() -> int:
    return g("\U0001f600", 1) + len(3)
"""


def test_columns_are_utf16_on_both_sides() -> None:
    current = EMOJI.replace(", 1)", ", int(1))")
    assert back_key(current, EMOJI, _key(ARG, 5, 33, 34)) == _key(ARG, 5, 28, 29)
    assert _realigned([_entry(ARG, 28, 29)], [], [_key(ARG, 5, 33, 34)], current, EMOJI) == [_entry(ARG, 33, 34)]


A, B, C = _entry(ARG, 16, 19), _entry(ARG, 27, 28), _entry("reportCallIssue", 4, 9)


def test_a_renamed_file_takes_its_entries_to_the_new_key() -> None:
    files = {"./pkg/m.py": [A, B], "./pkg/o.py": [C]}
    assert rekeyed(files, {"pkg/n.py": "pkg/m.py"}) == {"./pkg/n.py": [A, B], "./pkg/o.py": [C]}
    assert rekeyed({"./pkg/m.py": [A, B], "./pkg/n.py": [C]}, {"pkg/n.py": "pkg/m.py"}) == {"./pkg/n.py": [C, A, B]}
    assert files == {"./pkg/m.py": [A, B], "./pkg/o.py": [C]}


def test_renames_of_unlisted_files_change_nothing() -> None:
    files = {"./pkg/m.py": [A, B]}
    assert rekeyed(files, {"pkg/q.py": "pkg/p.py"}) == files
    assert rekeyed(files, {}) == files


def test_a_rename_onto_a_key_with_entries_merges_them_in_the_order_of_the_diagnostics() -> None:
    first, second, third = _entry(ARG, 12, 13), _entry(ARG, 13, 16), _entry(ARG, 12, 14)
    stale = _entry("reportCallIssue", 4, 9)
    now = [_key(ARG, 5, 12, 13), _key(ARG, 6, 13, 16), _key(ARG, 7, 12, 14)]
    assert _merged([stale, second], [first, third], [], now, OUT_OF_ORDER, OUT_OF_ORDER) == [stale, first, second, third]
    assert _merged([second], [first, stale, third], now[1:2], [now[0], now[2]], OUT_OF_ORDER, OUT_OF_ORDER) == [
        first, stale, second, third]
    assert _merged([stale], [first, second], [], [], OUT_OF_ORDER, OUT_OF_ORDER) == [stale, first, second]
