"""Python rename of a `Literal` member: the strings the checker types by that literal type, and nothing else."""

from __future__ import annotations

from pathlib import Path

import pytest
from project_files import file_tree, write_project
from refactor_cli import assert_same_run, line_col, read, run, template_regex

from living_architecture.contract import message

KINDS = 'from typing import Literal\n\nDriftKind = Literal["edit_model", "drop"]\n'
CONTEXTS = """\
from pkg.kinds import DriftKind


def f(kind: DriftKind) -> None:
    print(kind)


def call() -> None:
    f("edit_model")


k: DriftKind = "edit_model"


def ret() -> DriftKind:
    return 'edit_model'


def dflt(kind: DriftKind = "edit_model") -> None:
    print(kind)


xs: list[DriftKind] = ["edit_model"]


def cmp(kind: DriftKind) -> bool:
    return kind == "edit_model" or kind in ("edit_model",)


def m(kind: DriftKind) -> int:
    match kind:
        case "edit_model":
            return 1
        case "drop":
            return 2
"""
UNRELATED = """\
import argparse
from typing import Literal

Other = Literal["edit_model", "zzz"]


def g(o: Other) -> None:
    print(o)


def calls() -> None:
    g("edit_model")
    s: str = "edit_model"
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=["edit_model"])
    print(s, parser)
"""
SYMBOL = "DriftKind['edit_model']"


def _rename(rel: str, locator: list[str], new: str, *flags: str, apply: bool = True) -> list[str]:
    return [*(["--apply"] if apply else []), "rename", "--file", rel, *locator, "--new-name", new, *flags]


def _by_symbol(new: str = "edit_master", *flags: str, symbol: str = SYMBOL, rel: str = "pkg/kinds.py") -> list[str]:
    return _rename(rel, ["--symbol", symbol], new, *flags)


def test_python_contexts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_project(tmp_path / "proj", {"pkg/kinds.py": KINDS, "pkg/use.py": CONTEXTS})
    code, _out, err = run(root, _by_symbol(), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/kinds.py") == KINDS.replace("edit_model", "edit_master")
    assert read(root, "pkg/use.py") == CONTEXTS.replace("edit_model", "edit_master")


def test_unrelated_equal_strings_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/kinds.py": KINDS, "pkg/other.py": UNRELATED})
    code, _out, err = run(root, _by_symbol(), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/other.py") == UNRELATED


def test_unrelated_equal_strings_are_leftovers_with_docs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/kinds.py": KINDS, "pkg/other.py": UNRELATED})
    code, _out, err = run(root, _by_symbol("edit_master", "--docs"), monkeypatch, capsys)
    assert code == 0
    assert read(root, "pkg/other.py") == UNRELATED
    assert err.splitlines() == [
        message("refactor.leftover", path="pkg/other.py", line=line, where="string", old="edit_model")
        for line in (4, 12, 13, 15)
    ]


EXHAUSTIVE = """\
from typing import assert_never

from pkg.kinds import DriftKind


def m(kind: DriftKind) -> int:
    match kind:
        case "edit_model":
            return 1
        case "drop":
            return 2
        case _:
            assert_never(kind)
"""


def test_exhaustive_match_does_not_refuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/kinds.py": KINDS, "pkg/m.py": EXHAUSTIVE})
    code, _out, err = run(root, _by_symbol(), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/m.py") == EXHAUSTIVE.replace("edit_model", "edit_master")


NARROWED = """\
from pkg.kinds import DriftKind


def f(kind: DriftKind) -> None:
    print(kind)


def h() -> None:
    k = "edit_model"
    f(k)
    f("edit_model")
"""


def test_narrowed_local_refuses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_project(tmp_path / "proj", {"pkg/kinds.py": KINDS, "pkg/n.py": NARROWED})
    before = file_tree(root)
    code, out, err = run(root, _by_symbol(), monkeypatch, capsys)
    assert (code, out) == (1, "")
    lines = err.splitlines()
    assert lines[0] == message("refactor.literal-unresolved", path="pkg/n.py", line=10, old="edit_model")
    assert template_regex(message("refactor.blindspots", count=1, attr="ATTR"), attr="ATTR").fullmatch(lines[1])
    assert len(lines) == 2
    assert file_tree(root) == before


@pytest.mark.parametrize("flag", [["--allow-blindspots"], ["--keep", "pkg/n.py:10"]], ids=["allow", "keep"])
def test_narrowed_local_passes_with_allow_or_keep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], flag: list[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/kinds.py": KINDS, "pkg/n.py": NARROWED})
    code, _out, _err = run(root, _by_symbol("edit_master", *flag), monkeypatch, capsys)
    assert code == 0
    assert read(root, "pkg/n.py") == NARROWED.replace('f("edit_model")', 'f("edit_master")')


DERIVED = """\
from typing import Literal

from pkg.kinds import DriftKind

Ext = Literal[DriftKind, "x"]


def h(e: Ext) -> None:
    print(e)


def call() -> None:
    h("edit_model")
"""


def test_derived_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_project(tmp_path / "proj", {"pkg/kinds.py": KINDS, "pkg/d.py": DERIVED})
    code, _out, err = run(root, _by_symbol(), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/d.py") == DERIVED.replace("edit_model", "edit_master")


@pytest.mark.parametrize("value", ["it's", 'say "x"', "back\\slash", "two\nlines"],
                         ids=["single-quote", "double-quote", "backslash", "line-break"])
def test_value_with_a_quote_backslash_or_line_break_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], value: str
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/kinds.py": KINDS, "pkg/use.py": CONTEXTS})
    before = file_tree(root)
    expected = message("refactor.literal-value", value=value)
    assert run(root, _by_symbol(value), monkeypatch, capsys) == (2, "", f"{expected}\n")
    assert file_tree(root) == before


def test_new_value_need_not_be_an_identifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/kinds.py": KINDS, "pkg/use.py": CONTEXTS})
    code, _out, err = run(root, _by_symbol("edit-master v2"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/use.py") == CONTEXTS.replace("edit_model", "edit-master v2")


def test_located_on_the_string_inside_the_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"pkg/kinds.py": KINDS, "pkg/use.py": CONTEXTS}
    position = line_col(write_project(tmp_path / "probe", files), "pkg/kinds.py", "edit_model")
    assert_same_run(tmp_path, files, _by_symbol(), _rename("pkg/kinds.py", position, "edit_master"), monkeypatch,
                    capsys)


INLINE = """\
from typing import Literal


def g(mode: Literal["fast", "slow"]) -> None:
    print(mode)


def call() -> None:
    g("fast")
"""


def test_located_through_a_parameter_annotation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/g.py": INLINE})
    code, _out, err = run(root, _by_symbol("quick", symbol="g(mode)['fast']", rel="pkg/g.py"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/g.py") == INLINE.replace('"fast"', '"quick"')


def test_double_quoted_member_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    files = {"pkg/kinds.py": KINDS, "pkg/use.py": CONTEXTS}
    assert_same_run(tmp_path, files, _by_symbol(), _by_symbol(symbol='DriftKind["edit_model"]'), monkeypatch, capsys)
