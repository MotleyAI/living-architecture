"""Python wildcard symbol paths: `*.<locals>.NAME` and `Scope.*.<locals>.NAME` name every local of a name."""

from __future__ import annotations

from pathlib import Path

import pytest

from deterministic_refactor.contract import message
from project_files import file_tree, write_project
from refactor_cli import entry_refusal, read, run, template_regex

SOURCE = """\
def f(name: str) -> str:
    model = name.upper()

    def inner() -> str:
        model = name.lower()
        return model

    return model + inner()


class Query:
    def run(self, name: str) -> str:
        model = name.title()

        def step() -> str:
            model = name.strip()
            return model

        return model + step()

    def plan(self, name: str) -> str:
        for model in name:
            print(model)
        return name


def h(model: str) -> str:
    return model


def k(name: str) -> str:
    modle = name
    return modle
"""
RENAMED = SOURCE.replace("model", "dataset")
H = "def h(model: str) -> str:\n    return model\n"


def _region(text: str, start: str, end: str) -> str:
    return text[text.index(start):text.index(end)]


def _map(root: Path, *entries: str) -> list[str]:
    (root / "map.yaml").write_text("".join(f"- {entry}\n" for entry in entries), encoding="utf-8")
    return ["--apply", "rename-map", "map.yaml"]


def _wild(symbol: str, intent: str = "new_name: dataset") -> str:
    return f"{{file: pkg/l.py, symbol: '{symbol}', {intent}}}"


def test_a_file_wide_wildcard_renames_every_local_and_no_parameter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/l.py": SOURCE})
    code, _out, err = run(root, _map(root, _wild("*.<locals>.model")), monkeypatch, capsys)
    assert (code, err, read(root, "pkg/l.py")) == (0, "", RENAMED.replace(H.replace("model", "dataset"), H))


def test_a_class_scoped_wildcard_renames_the_locals_nested_at_any_depth_inside_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/l.py": SOURCE})
    code, _out, err = run(root, _map(root, _wild("Query.*.<locals>.model")), monkeypatch, capsys)
    query = _region(SOURCE, "class Query:", "def h(")
    assert (code, err, read(root, "pkg/l.py")) == (0, "", SOURCE.replace(query, query.replace("model", "dataset")))


def test_a_function_scoped_wildcard_renames_the_locals_of_the_functions_nested_inside_it_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/l.py": SOURCE})
    code, _out, err = run(root, _map(root, _wild("f.*.<locals>.model")), monkeypatch, capsys)
    inner = _region(SOURCE, "    def inner()", "    return model + inner()")
    assert (code, err, read(root, "pkg/l.py")) == (0, "", SOURCE.replace(inner, inner.replace("model", "dataset")))


def test_a_wildcard_equals_one_entry_per_local(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    left = write_project(tmp_path / "left", {"pkg/l.py": SOURCE})
    right = write_project(tmp_path / "right", {"pkg/l.py": SOURCE})
    explicit = [f"{{file: pkg/l.py, symbol: {path}.<locals>.model, new_name: dataset}}"
                for path in ("Query.run", "Query.run.<locals>.step", "Query.plan")]
    expected = run(left, _map(left, *explicit), monkeypatch, capsys)
    actual = run(right, _map(right, _wild("Query.*.<locals>.model")), monkeypatch, capsys)
    out = expected[1].replace(message("refactor.rename-header", old="model", new="dataset") + "\n", "", 2)
    assert (actual, read(right, "pkg/l.py")) == ((0, out, ""), read(left, "pkg/l.py"))


def test_rename_takes_a_wildcard_symbol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/l.py": SOURCE})
    argv = ["--apply", "rename", "--file", "pkg/l.py", "--symbol", "Query.*.<locals>.model", "--new-name", "dataset"]
    code, out, err = run(root, argv, monkeypatch, capsys)
    assert (code, out.count(message("refactor.rename-header", old="model", new="dataset")), err,
            "dataset = name.title()" in read(root, "pkg/l.py")) == (0, 1, "", True)


NO_MATCH: dict[str, tuple[str, str | None]] = {
    "file-wide": ("*.<locals>.modell", "Query, f, h, k"),
    "class-scoped": ("Query.*.<locals>.modle", "plan, run"),
    "function-scoped": ("k.*.<locals>.model", "modle"),
    "star-first-then-a-member": ("*.model", None),
    "star-last": ("f.<locals>.*", None),
    "star-alone": ("*", None),
    "two-stars": ("*.*.<locals>.model", None),
    "star-inside-a-segment": ("Qu*.<locals>.model", None),
    "with-a-parameter": ("*.<locals>.inner(x)", None),
    "with-a-literal-value": ("*.<locals>.model['x']", None),
}


@pytest.mark.parametrize(("symbol", "candidates"), NO_MATCH.values(), ids=NO_MATCH.keys())
def test_a_wildcard_that_locates_nothing_or_is_misplaced_is_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], symbol: str, candidates: str | None
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/l.py": SOURCE})
    before = file_tree(root)
    argv = ["--apply", "rename", "--file", "pkg/l.py", "--symbol", symbol, "--new-name", "dataset"]
    code, out, err = run(root, argv, monkeypatch, capsys)
    # A misplaced `*` is unresolved like any path; which scope's names it lists is not pinned.
    listed = "CANDIDATES" if candidates is None else candidates
    unresolved = message("refactor.symbol-unresolved", path="pkg/l.py", symbol=symbol, candidates=listed)
    expected = template_regex(entry_refusal(f"pkg/l.py {symbol}", unresolved) + "\n", any="CANDIDATES")
    assert (code, out, expected.fullmatch(err) is not None, file_tree(root) == before) == (2, "", True, True)


WILDCARD = message("refactor.symbol-wildcard", path="pkg/l.py", symbol="*.<locals>.model")
# The refusal of entry 1 located by the entry's own symbol.
BY_WILDCARD = entry_refusal("pkg/l.py *.<locals>.model", WILDCARD) + "\n"
BY_F = entry_refusal("pkg/l.py f", WILDCARD) + "\n"
REFUSED: dict[str, tuple[list[str], str]] = {
    "retarget-symbol": (["retarget", "--file", "pkg/l.py", "--symbol", "*.<locals>.model", "--target", "f"], BY_WILDCARD),
    "retarget-target": (["retarget", "--file", "pkg/l.py", "--symbol", "f", "--target", "*.<locals>.model"], BY_F),
    "move-symbol": (["move-symbol", "--file", "pkg/l.py", "--symbol", "*.<locals>.model", "--dest", "pkg/d.py"],
                    WILDCARD + "\n"),
}


@pytest.mark.parametrize(("argv", "expected"), REFUSED.values(), ids=REFUSED.keys())
def test_only_a_rename_takes_a_wildcard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], argv: list[str], expected: str
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/l.py": SOURCE, "pkg/d.py": ""})
    before = file_tree(root)
    assert (run(root, ["--apply", *argv], monkeypatch, capsys), file_tree(root) == before) == ((2, "", expected), True)


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        (_wild("*.<locals>.model", "retarget: f"), BY_WILDCARD),
        ("{file: pkg/l.py, symbol: f, retarget: '*.<locals>.model'}", BY_F),
    ],
    ids=["symbol", "retarget"],
)
def test_a_retarget_entry_refuses_a_wildcard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], entry: str, expected: str
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/l.py": SOURCE})
    assert run(root, _map(root, entry), monkeypatch, capsys) == (2, "", expected)


def test_a_wildcard_and_an_entry_for_one_of_its_locals_merge_or_are_duplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/l.py": SOURCE})
    one = "{file: pkg/l.py, symbol: Query.run.<locals>.model, new_name: %s}"
    duplicate = run(root, _map(root, _wild("Query.*.<locals>.model"), one % "table"), monkeypatch, capsys)
    merged = run(root, _map(root, _wild("Query.*.<locals>.model"), one % "dataset"), monkeypatch, capsys)
    expected = message("refactor.map-duplicate", map="map.yaml", first=1, second=2) + "\n"
    assert (duplicate, merged[0], merged[2], "table" in read(root, "pkg/l.py")) == ((2, "", expected), 0, "", False)


def test_two_wildcards_reaching_one_local_with_different_names_are_duplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/l.py": SOURCE})
    argv = _map(root, _wild("*.<locals>.model"), _wild("Query.*.<locals>.model", "new_name: table"))
    expected = message("refactor.map-duplicate", map="map.yaml", first=1, second=2) + "\n"
    assert run(root, argv, monkeypatch, capsys) == (2, "", expected)


CONFLICT = SOURCE + "\n\ndef taken(name: str) -> str:\n    dataset = name\n    model = name\n    return model + dataset\n"


def test_one_conflicting_local_refuses_the_whole_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/l.py": CONFLICT})
    before = file_tree(root)
    code, out, err = run(root, _map(root, _wild("*.<locals>.model")), monkeypatch, capsys)
    conflict = message("refactor.name-conflict", name="dataset", path="pkg/l.py", line=37)
    expected = entry_refusal("pkg/l.py *.<locals>.model", conflict) + "\n"
    assert (code, out, err, file_tree(root) == {**before, "map.yaml": (root / "map.yaml").read_bytes()}) == (
        1, "", expected, True)
