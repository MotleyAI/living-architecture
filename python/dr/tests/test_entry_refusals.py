"""Python `dr-refactor`: a refusal names its entry and locator, is printed once, and site paths resolve against the
project; the own-scope name check runs before any reference search."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from deterministic_refactor.contract import message
from deterministic_refactor.refactor.rename_union import SymbolRename
from deterministic_refactor.refactor.sites import Keeps, Site
from deterministic_refactor.refactor.symbol_path import LocatorError
from project_files import file_tree, write_project
from refactor_cli import entry_refusal, run, run_raw

CHECKS = "[resolve]\n[checks]\n"
REFERENCES = message("refactor.progress-phase", phase="references")
CONFLICTS = message("refactor.progress-phase", phase="conflicts")
A = "def foo() -> int:\n    return 1\n"
CANNOT = message("refactor.cannot-rename")


# ---- the entry and its locator


@pytest.mark.parametrize(
    ("locator", "shown", "finding", "code"),
    [
        (["--line", "2", "--col", "5"], "pkg/a.py:2:5", CANNOT, 1),
        (["--line", "99"], "pkg/a.py:99", message("refactor.line-out-of-range", line=99, count=2), 1),
        (["--symbol", "nope"], "pkg/a.py nope",
         message("refactor.symbol-unresolved", path="pkg/a.py", symbol="nope", candidates="foo"), 2),
        (["--offset", "999"], "pkg/a.py offset 999", message("refactor.offset-out-of-range", offset=999, count=len(A)), 1),
    ],
    ids=["line-col", "line", "symbol", "offset"],
)
def test_a_rename_that_does_not_resolve_names_entry_1_and_its_locator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], locator: list[str], shown: str,
    finding: str, code: int,
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/a.py": A})
    argv = ["rename", "--file", "pkg/a.py", *locator, "--new-name", "bar"]
    assert run_raw(root, argv, monkeypatch, capsys) == (code, "", CHECKS + entry_refusal(shown, finding) + "\n")


def test_a_module_entry_is_located_by_its_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/a.py": A, "pkg/b.py": "Y = 1\n"})
    conflict = message("refactor.name-conflict", name="b", path="pkg/b.py", line=1)
    argv = ["rename", "--file", "pkg/a.py", "--new-name", "b"]
    assert run_raw(root, argv, monkeypatch, capsys) == (1, "", CHECKS + entry_refusal("pkg/a.py", conflict) + "\n")


def test_a_locator_is_printed_relative_to_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/a.py": A})
    argv = ["rename", "--file", str(root / "pkg" / "a.py"), "--line", "99", "--new-name", "bar"]
    refused = entry_refusal("pkg/a.py:99", message("refactor.line-out-of-range", line=99, count=2))
    assert run_raw(root, argv, monkeypatch, capsys) == (1, "", CHECKS + refused + "\n")


def test_merged_entries_are_named_together_with_the_first_ones_locator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"pkg/a.py": "old = 1\n\n\ndef f() -> int:\n    fresh = 2\n    return old + fresh\n"}
    entries = [{"file": "pkg/a.py", "symbol": "old", "new_name": "fresh"},
               {"file": "pkg/a.py", "line": 1, "col": 1, "new_name": "fresh"}]
    root = write_project(tmp_path / "proj", {**files, "map.yaml": yaml.safe_dump(entries, sort_keys=False)})
    code, out, err = run(root, ["rename-map", "map.yaml"], monkeypatch, capsys)
    conflict = message("refactor.name-conflict", name="fresh", path="pkg/a.py", line=5)
    assert (code, out, err) == (1, "", entry_refusal("pkg/a.py old", conflict, 1, 2) + "\n")


# ---- each refusal once, the exit code apart from where it is printed

STAND_IN = "class A:\n    def m(self) -> int:\n        return 1\n\n\nclass B:\n    def m(self) -> int:\n        return 2\n"


@pytest.mark.parametrize("flags", [[], ["--fail-fast"]], ids=["default", "fail-fast"])
def test_a_refusal_printed_under_its_group_still_sets_the_exit_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], flags: list[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/a.py": STAND_IN})
    argv = ["--apply", "rename", "--file", "pkg/a.py", "--symbol", "A.m", "--new-name", "n", *flags]
    before = file_tree(root)
    code, out, err = run_raw(root, argv, monkeypatch, capsys)
    stand_in = message("refactor.stand-in", path="pkg/a.py", line=7, cls="B", attr="m")
    refused = message("refactor.progress-refused", phase="rules", n=1, count=1,
                      entries=message("refactor.progress-entry", index=1), old="m", new="n", refusals=1)
    assert (code, out) == (1, "")
    assert err.splitlines()[-2 - (not flags):] == [refused, stand_in, *([] if flags else [CONFLICTS])]
    assert err.count(stand_in) == 1
    assert file_tree(root) == before


def test_the_exit_code_is_the_highest_of_the_refusals_printed_anywhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/a.py": A})

    def failing(self: SymbolRename, index: object, facts: object) -> None:
        raise LocatorError("no such thing")

    monkeypatch.setattr(SymbolRename, "_index_edits", failing)
    code, out, err = run(root, ["rename", "--file", "pkg/a.py", "--symbol", "foo", "--new-name", "bar"], monkeypatch, capsys)
    assert (code, out, err) == (2, "", entry_refusal("pkg/a.py foo", "no such thing") + "\n")


# ---- sites resolve against the project


def test_a_site_is_resolved_against_the_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = write_project(tmp_path.resolve() / "proj", {"pkg/a.py": A})
    monkeypatch.chdir(tmp_path)
    assert Site.parse("pkg/a.py:2", root).covers("pkg/a.py", 2)
    assert not Site.parse("pkg/a.py:2", root).missing(root)
    assert Site.parse(f"{root}/pkg/a.py:2", root).covers("pkg/a.py", 2)
    assert Site.parse("proj/pkg/a.py:2", root).parts is None
    assert Site.parse("proj/pkg/a.py:2", root).missing(root)


def test_keeps_are_resolved_against_the_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = write_project(tmp_path.resolve() / "proj", {"pkg/a.py": A})
    monkeypatch.chdir(tmp_path)
    keeps = Keeps(("pkg/a.py:2", "proj/pkg/a.py:1"), root)
    assert [keeps.kept("pkg/a.py", 2), keeps.kept("pkg/a.py", 1)] == [True, False]
    assert keeps.unmatched() == ["proj/pkg/a.py:1"]


USE = "from pkg.a import foo\n\nx = foo()\ny = foo()\n"


@pytest.mark.parametrize("absolute", [False, True], ids=["relative", "absolute"])
def test_a_keep_is_relative_to_the_project_from_another_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], absolute: bool
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/a.py": A, "pkg/use.py": USE})
    keep = f"{root.resolve() / 'pkg' / 'use.py'}:3" if absolute else "pkg/use.py:3"
    monkeypatch.chdir(tmp_path)
    argv = ["--project", "proj", "--apply", "rename", "--file", "proj/pkg/a.py", "--symbol", "foo", "--new-name", "bar",
            "--keep", keep]
    code, _out, err = run(tmp_path, argv, monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert (root / "pkg" / "use.py").read_text(encoding="utf-8") == "from pkg.a import bar\n\nx = foo()\ny = bar()\n"


def test_a_keep_relative_to_the_working_directory_names_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_project(tmp_path / "proj", {"pkg/a.py": A, "pkg/use.py": USE})
    monkeypatch.chdir(tmp_path)
    argv = ["--project", "proj", "rename", "--file", "proj/pkg/a.py", "--symbol", "foo", "--new-name", "bar",
            "--keep", "proj/pkg/use.py:3"]
    missing = message("refactor.site-missing", option="--keep", site="proj/pkg/use.py:3")
    assert run_raw(tmp_path, argv, monkeypatch, capsys) == (2, "", CHECKS + missing + "\n")


NOTED = USE + "# foo is called twice\n"


def test_a_pick_is_relative_to_the_project_from_another_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/a.py": A, "pkg/use.py": NOTED})
    monkeypatch.chdir(tmp_path)
    argv = ["--project", "proj", "--apply", "rename", "--file", "proj/pkg/a.py", "--symbol", "foo", "--new-name", "bar",
            "--docs", "--docs-pick", "pkg/use.py:5"]
    code, _out, err = run(tmp_path, argv, monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert (root / "pkg" / "use.py").read_text(encoding="utf-8") == NOTED.replace("foo", "bar")


def test_a_pick_relative_to_the_working_directory_names_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    write_project(tmp_path / "proj", {"pkg/a.py": A, "pkg/use.py": NOTED})
    monkeypatch.chdir(tmp_path)
    argv = ["--project", "proj", "rename", "--file", "proj/pkg/a.py", "--symbol", "foo", "--new-name", "bar",
            "--docs", "--docs-pick", "proj/pkg/use.py:5"]
    missing = message("refactor.site-missing", option="--docs-pick", site="proj/pkg/use.py:5")
    assert run_raw(tmp_path, argv, monkeypatch, capsys) == (2, "", CHECKS + missing + "\n")


# ---- the own-scope check

MEMBER = "class C:\n    def old(self) -> int:\n        return 1\n\n{body}"
OWN_SCOPE = {
    "method": (MEMBER.format(body="    def fresh(self) -> int:\n        return 2\n"), "C.old", 5),
    "class-attribute": (MEMBER.format(body="    fresh: int = 0\n"), "C.old", 5),
    "property": (MEMBER.format(body="    @property\n    def fresh(self) -> int:\n        return 2\n"), "C.old", 6),
    "self-attribute": (MEMBER.format(body="    def set(self) -> None:\n        self.fresh = 2\n"), "C.old", 6),
    "parameter": ("def f(old: int, fresh: int) -> int:\n    return old - fresh\n", "f(old)", 1),
    "keyword-only": ("def f(old: int, *, fresh: int) -> int:\n    return old - fresh\n", "f(old)", 1),
    "local": ("def f(old: int) -> int:\n    fresh = 2\n    return old - fresh\n", "f(old)", 2),
    "loop-target": ("def f(old: int) -> int:\n    for fresh in range(old):\n        pass\n    return old\n", "f(old)", 2),
    "top-level": ("old = 1\nfresh = 2\n", "old", 2),
    "import-alias": ("import os as fresh\n\nold = 1\nprint(fresh.sep)\n", "old", 1),
    "function": ("old = 1\n\n\ndef fresh() -> int:\n    return 2\n", "old", 4),
}


@pytest.mark.parametrize(("text", "symbol", "line"), list(OWN_SCOPE.values()), ids=list(OWN_SCOPE))
def test_a_new_name_the_declaring_scope_holds_is_refused_before_any_reference_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], text: str, symbol: str, line: int
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/m.py": text})
    argv = ["rename", "--file", "pkg/m.py", "--symbol", symbol, "--new-name", "fresh"]
    conflict = message("refactor.name-conflict", name="fresh", path="pkg/m.py", line=line)
    refused = entry_refusal(f"pkg/m.py {symbol}", conflict)
    assert run_raw(root, argv, monkeypatch, capsys) == (1, "", CHECKS + refused + "\n")


OTHER_SCOPE = {
    "nested-function": "def f(old: int) -> int:\n    def inner() -> int:\n        fresh = 2\n        return fresh\n\n    return old + inner()\n",
    "comprehension": "def f(old: int) -> int:\n    return old + len([fresh for fresh in range(3)])\n",
    "nested-class": "def f(old: int) -> int:\n    class Box:\n        fresh = 3\n\n    return old + Box.fresh\n",
    "another-function": "def f(old: int) -> int:\n    return old\n\n\ndef g(fresh: int) -> int:\n    return fresh\n",
}


@pytest.mark.parametrize("text", list(OTHER_SCOPE.values()), ids=list(OTHER_SCOPE))
def test_a_new_name_another_scope_binds_passes_the_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], text: str
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/m.py": text})
    argv = ["--apply", "rename", "--file", "pkg/m.py", "--symbol", "f(old)", "--new-name", "fresh"]
    code, _out, err = run_raw(root, argv, monkeypatch, capsys)
    assert code == 0, err
    assert REFERENCES in err.splitlines()


INHERITED = "class Base:\n    def fresh(self) -> int:\n        return 2\n\n\nclass C(Base):\n    def old(self) -> int:\n        return 1\n"
CAPTURED = "old = 1\n\n\ndef f() -> int:\n    fresh = 2\n    return old + fresh\n"


@pytest.mark.parametrize(
    ("text", "symbol", "line"),
    [(INHERITED, "C.old", 2), (CAPTURED, "old", 5)],
    ids=["inherited-member", "captured-read"],
)
def test_a_conflict_outside_the_declaring_scope_is_left_to_the_conflicts_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], text: str, symbol: str, line: int
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/m.py": text})
    argv = ["rename", "--file", "pkg/m.py", "--symbol", symbol, "--new-name", "fresh"]
    code, out, err = run_raw(root, argv, monkeypatch, capsys)
    conflict = message("refactor.name-conflict", name="fresh", path="pkg/m.py", line=line)
    assert (code, out) == (1, "")
    assert err.splitlines()[-2:] == [CONFLICTS, entry_refusal(f"pkg/m.py {symbol}", conflict)]


def _map(entries: list[dict[str, object]]) -> str:
    return yaml.safe_dump(entries, sort_keys=False)


PAIR = "def f(x: int, y: int) -> int:\n    return x - y\n"


def test_a_name_another_entry_frees_is_not_refused_in_the_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    entries: list[dict[str, object]] = [{"file": "pkg/f.py", "symbol": "f(x)", "new_name": "y"},
                                        {"file": "pkg/f.py", "symbol": "f(y)", "new_name": "z"}]
    root = write_project(tmp_path / "proj", {"pkg/f.py": PAIR, "map.yaml": _map(entries)})
    code, _out, err = run(root, ["--apply", "rename-map", "map.yaml"], monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert (root / "pkg" / "f.py").read_text(encoding="utf-8") == "def f(y: int, z: int) -> int:\n    return y - z\n"

