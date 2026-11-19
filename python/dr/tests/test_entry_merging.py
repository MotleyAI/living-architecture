"""Map entries that locate the same symbol are merged: different new names make them a map duplicate."""

from __future__ import annotations

from pathlib import Path

import pytest

from deterministic_refactor.contract import message
from entry_source import ALT, OTHER, M, line
from project_files import write_project
from refactor_cli import run


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return write_project(tmp_path / "proj", {"pkg/m.py": M, "pkg/other.py": OTHER, "pkg/alt.py": ALT})


# Pairs of entries locating the same symbol: different new names make them a map duplicate.
SAME_SYMBOL = [
    ("overloads", "{symbol: Box.get}", f"{{line: {line('def get', 2)}, col: 9}}"),
    ("property-getter-and-setter", "{symbol: Box.label}", f"{{line: {line('def label', 1)}, col: 9}}"),
    ("conditional-assignments", f"{{line: {line('MODE = 1')}, col: 5}}", f"{{line: {line('MODE = 2')}, col: 5}}"),
    ("repeated-assignments", f"{{line: {line('local = a')}, col: 5}}", f"{{line: {line('local += 1')}, col: 5}}"),
]


@pytest.mark.parametrize(("first", "second"), [row[1:] for row in SAME_SYMBOL], ids=[row[0] for row in SAME_SYMBOL])
def test_entries_locating_the_same_symbol_are_merged(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], first: str, second: str
) -> None:
    entry = "- {{file: pkg/m.py, {locator}, new_name: {new}}}\n"
    (root / "map.yaml").write_text("".join(entry.format(locator=loc.strip("{}"), new=new)
                                           for loc, new in ((first, "fresh"), (second, "other_name"))), encoding="utf-8")
    duplicate = message("refactor.map-duplicate", map="map.yaml", first=1, second=2)
    assert run(root, ["rename-map", "map.yaml"], monkeypatch, capsys) == (2, "", duplicate + "\n")


def test_an_import_binding_entry_merges_with_its_declarations_entry(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (root / "map.yaml").write_text("- {file: pkg/other.py, symbol: thing, new_name: fresh}\n"
                                   "- {file: pkg/m.py, symbol: thing, new_name: other_name}\n", encoding="utf-8")
    duplicate = message("refactor.map-duplicate", map="map.yaml", first=1, second=2)
    assert run(root, ["rename-map", "map.yaml"], monkeypatch, capsys) == (2, "", duplicate + "\n")


# Two groups binding `x` on one line: (file text, the line, a column in each group, the file renamed y and z).
SAME_LINE = [
    ("comprehensions", "def f(xs, ys):\n    a = [x for x in xs]; b = [x for x in ys]\n    return a, b\n", 2, (10, 37),
     "def f(xs, ys):\n    a = [y for y in xs]; b = [z for z in ys]\n    return a, b\n"),
    ("lambdas", "f = lambda x: x; g = lambda x: x\n", 1, (12, 32), "f = lambda y: y; g = lambda z: z\n"),
]


@pytest.mark.parametrize(("text", "row", "cols", "renamed"), [r[1:] for r in SAME_LINE], ids=[r[0] for r in SAME_LINE])
@pytest.mark.parametrize("same_name", [False, True], ids=["different-names", "same-name"])
def test_two_groups_on_one_line_are_separate_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    text: str, row: int, cols: tuple[int, int], renamed: str, same_name: bool,
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/s.py": text})
    news = ("y", "y") if same_name else ("y", "z")
    (root / "map.yaml").write_text("".join(f"- {{file: pkg/s.py, line: {row}, col: {col}, new_name: {new}}}\n"
                                           for col, new in zip(cols, news, strict=True)), encoding="utf-8")
    assert run(root, ["--apply", "rename-map", "map.yaml"], monkeypatch, capsys)[0] == 0
    expected = renamed.replace("z", "y") if same_name else renamed
    assert (root / "pkg" / "s.py").read_text(encoding="utf-8") == expected
