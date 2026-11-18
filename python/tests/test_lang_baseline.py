"""The basedpyright baseline pieces `dr-refactor` and `la-typecheck --realign-from` share."""

from pathlib import Path

from living_architecture.lang.baseline import Key, baselined, diagnostics, marked, matches, pairs, text_edits
from living_architecture.lang.position_map import Edit, map_range

ARG = "reportArgumentType"


def _entry(code: str, start: int, end: int, lines: int | None = 1) -> dict[str, object]:
    rng: dict[str, object] = {"startColumn": start, "endColumn": end}
    if lines is not None:
        rng["lineCount"] = lines
    return {"code": code, "range": rng}


def test_text_edits_are_the_changed_characters_of_the_changed_lines() -> None:
    old = 'a = 1\nreturn f(1, "x")\nb = 2\n'
    new = 'a = 1\nreturn f(int(1), "x")\nb = 2\n'
    edits: list[Edit] = text_edits(old, new)
    assert edits == [(15, 15, 4), (16, 16, 1)]
    assert map_range(edits, old.index('"x"'), old.index('"x"') + 3) == (new.index('"x"'), new.index('"x"') + 3)


def test_a_range_in_removed_text_maps_to_an_empty_range() -> None:
    old = "a = 1\nprint(len(4))\nb = 2\n"
    edits = text_edits(old, "a = 1\nb = 2\n")
    start, end = map_range(edits, old.index("4"), old.index("4") + 1)
    assert start == end


def test_an_entry_matches_on_rule_columns_and_line_count() -> None:
    key: Key = (ARG, 5, 16, 5, 19)
    assert matches(_entry(ARG, 16, 19), key)
    assert matches(_entry(ARG, 16, 19, None), key)
    assert not matches(_entry("reportCallIssue", 16, 19), key)
    assert not matches(_entry(ARG, 16, 20), key)
    assert not matches(_entry(ARG, 16, 19, 2), key)
    assert matches(_entry(ARG, 16, 19, 2), (ARG, 5, 16, 6, 19))


def test_pairs_take_entries_in_list_order() -> None:
    entries = [_entry(ARG, 1, 2), _entry(ARG, 3, 4), _entry(ARG, 1, 2)]
    first, second, other = (ARG, 0, 1, 0, 2), (ARG, 4, 1, 4, 2), (ARG, 2, 3, 2, 4)
    assert pairs(entries, [first, other, second]) == [(0, first), (1, other), (2, second)]
    assert pairs(entries, [other, first, second]) == [(1, other), (2, first)]


def test_baselined_are_the_diagnostics_the_baseline_hides() -> None:
    a, b = ("m.py", (ARG, 0, 1, 0, 2)), ("m.py", (ARG, 3, 1, 3, 2))
    assert baselined([a, b, a], [a]) == [b, a]
    assert baselined([a, b], []) == [a, b]


def test_diagnostics_are_read_repo_relative_in_report_order(tmp_path: Path) -> None:
    def item(path: Path, line: int) -> dict[str, object]:
        return {"file": str(path), "rule": ARG,
                "range": {"start": {"line": line, "character": 1}, "end": {"line": line, "character": 2}}}

    report = {"generalDiagnostics": [item(tmp_path / "pkg/m.py", 3), item(tmp_path.parent / "outside.py", 0),
                                     item(tmp_path / "pkg/m.py", 7)]}
    assert diagnostics(report, tmp_path.resolve()) == [("pkg/m.py", (ARG, 3, 1, 3, 2)), ("pkg/m.py", (ARG, 7, 1, 7, 2))]


def test_a_diagnostic_without_a_range_is_left_out(tmp_path: Path) -> None:
    ranged = {"file": str(tmp_path / "m.py"), "rule": ARG,
              "range": {"start": {"line": 3, "character": 1}, "end": {"line": 3, "character": 2}}}
    report = {"generalDiagnostics": [{"file": str(tmp_path / "m.py"), "rule": "reportImportCycles"}, ranged]}
    assert diagnostics(report, tmp_path.resolve()) == [("m.py", (ARG, 3, 1, 3, 2))]


def test_marked_are_all_the_diagnostics_in_report_order() -> None:
    a, b = ("m.py", (ARG, 0, 1, 0, 2)), ("m.py", (ARG, 3, 1, 3, 2))
    assert marked([a, b, a], [a]) == [(*a, False), (*b, True), (*a, True)]
