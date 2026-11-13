"""Character-span edits over one snapshot: merge, overlap refusal, application."""

import pytest

from living_architecture.refactor.text_edits import OverlappingEdits, TextEdit, apply_edits, merge_edits


def _edit(start: int, end: int, text: str = "new", path: str = "m.py") -> TextEdit:
    return TextEdit(path=path, start=start, end=end, new_text=text)


def test_identical_edits_merge() -> None:
    assert merge_edits([_edit(4, 7), _edit(0, 3), _edit(4, 7)]) == [_edit(0, 3), _edit(4, 7)]


def test_edits_sort_by_path_then_start() -> None:
    edits = [_edit(5, 6, path="b.py"), _edit(9, 10), _edit(1, 2, path="b.py"), _edit(0, 1)]
    assert merge_edits(edits) == [_edit(0, 1), _edit(9, 10), _edit(1, 2, path="b.py"), _edit(5, 6, path="b.py")]


def test_adjacent_edits_do_not_overlap() -> None:
    assert merge_edits([_edit(3, 6), _edit(0, 3)]) == [_edit(0, 3), _edit(3, 6)]


@pytest.mark.parametrize(
    "edits",
    [[_edit(0, 4), _edit(2, 6)], [_edit(0, 3, "a"), _edit(0, 3, "b")], [_edit(0, 6), _edit(2, 3)]],
    ids=["partial", "same-span-other-text", "nested"],
)
def test_overlapping_edits_are_refused(edits: list[TextEdit]) -> None:
    with pytest.raises(OverlappingEdits):
        merge_edits(edits)


def test_same_spans_in_different_files_do_not_overlap() -> None:
    assert len(merge_edits([_edit(0, 3), _edit(0, 3, "b", path="b.py")])) == 2


def test_apply_edits_replaces_only_the_spans() -> None:
    text = 'r: "Rec | None" = Rec()\r\n😀 = 1'
    spans = [_edit(text.index("Rec"), text.index("Rec") + 3, "Recommendation"),
             _edit(text.rindex("Rec"), text.rindex("Rec") + 3, "Recommendation")]
    assert apply_edits(text, merge_edits(spans)) == 'r: "Recommendation | None" = Recommendation()\r\n😀 = 1'
