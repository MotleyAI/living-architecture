"""Python rename of a `Literal` member: the strings the checker types by that literal type, and nothing else."""

from __future__ import annotations

from pathlib import Path

import pytest
from project_files import file_tree, write_project
from refactor_cli import assert_same_run, entry_refusal, line_col, read, run, template_regex

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


def _leftovers(path: str, *lines: int) -> list[str]:
    return [message("refactor.leftover", path=path, line=line, where="string", old="edit_model") for line in lines]


@pytest.mark.parametrize("flags", [(), ("--docs",)], ids=["without-docs", "with-docs"])
def test_unrelated_equal_strings_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], flags: tuple[str, ...]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/kinds.py": KINDS, "pkg/other.py": UNRELATED})
    code, _out, err = run(root, _by_symbol("edit_master", *flags), monkeypatch, capsys)
    assert code == 0
    assert read(root, "pkg/other.py") == UNRELATED
    # The `Other` declaration, the `str` variable and `choices` are listed; the `Other`-typed argument is not.
    assert err.splitlines() == _leftovers("pkg/other.py", 4, 13, 15)


LOOSE = """\
from typing import Literal

Other = Literal["edit_model", "zzz"]


def h(o: Other | str) -> None:
    print(o)


def n(o: int) -> None:
    print(o)


def calls() -> None:
    h("edit_model")
    n("edit_model")
"""


def test_position_that_accepts_any_string_is_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/kinds.py": KINDS, "pkg/loose.py": LOOSE})
    code, _out, err = run(root, _by_symbol(), monkeypatch, capsys)
    assert code == 0
    assert read(root, "pkg/loose.py") == LOOSE
    assert err.splitlines() == _leftovers("pkg/loose.py", 3, 15, 16)


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
    k = "drop"
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
    assert lines[0] == message("refactor.literal-unresolved", path="pkg/n.py", line=11, old="edit_model")
    assert template_regex(message("refactor.blindspots", count=1, attr="ATTR"), attr="ATTR").fullmatch(lines[1])
    assert len(lines) == 2
    assert file_tree(root) == before


@pytest.mark.parametrize("flag", [["--allow-blindspots"], ["--keep", "pkg/n.py:11"]], ids=["allow", "keep"])
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


@pytest.mark.parametrize("value", ["it's", 'say "x"', "back\\slash", "two\nlines", "tick`tock", "a${b}", "para\u2029graph",
                                   "nul\x00"],
                         ids=["single-quote", "double-quote", "backslash", "line-break", "backtick", "interpolation",
                              "paragraph-separator", "nul"])
def test_value_with_a_quote_backslash_or_line_break_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], value: str
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/kinds.py": KINDS, "pkg/use.py": CONTEXTS})
    before = file_tree(root)
    expected = entry_refusal(f"pkg/kinds.py {SYMBOL}", message("refactor.literal-value", value=value))
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


def test_a_source_in_an_excluded_directory_is_not_probed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/kinds.py": KINDS, "pkg/use.py": CONTEXTS, "venv/lib/use.py": CONTEXTS})
    code, _out, err = run(root, _by_symbol(), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "venv/lib/use.py") == CONTEXTS


ESCAPED = 'from typing import Literal\n\nState = Literal["\\x72eady", "drop"]\n\ns: State = "\\x72eady"\n'


def test_an_escaped_member_is_renamed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_project(tmp_path / "proj", {"pkg/state.py": ESCAPED})
    code, _out, err = run(root, _by_symbol("done", symbol="State['ready']", rel="pkg/state.py"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/state.py") == ESCAPED.replace('"\\x72eady"', '"done"')


def test_an_implicitly_concatenated_member_cannot_be_renamed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/state.py": 'from typing import Literal\n\nState = Literal["re" "ady", "drop"]\n'})
    before = file_tree(root)
    code, _out, err = run(root, _by_symbol("done", symbol="State['ready']", rel="pkg/state.py"), monkeypatch, capsys)
    assert (code, err) == (1, entry_refusal("pkg/state.py State['ready']", message("refactor.cannot-rename")) + "\n")
    assert file_tree(root) == before


def test_a_literal_path_ignores_strings_outside_the_literal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    text = 'from typing import Annotated, Literal\n\nState = Annotated[Literal["ready", "drop"], "ready"]\n'
    root = write_project(tmp_path / "proj", {"pkg/state.py": text})
    code, _out, err = run(root, _by_symbol("done", symbol="State['ready']", rel="pkg/state.py"), monkeypatch, capsys)
    assert (code, err) == (0, message("refactor.leftover", path="pkg/state.py", line=3, where="string", old="ready") + "\n")
    assert read(root, "pkg/state.py") == text.replace('Literal["ready"', 'Literal["done"')


def test_a_qualified_type_alias_body_holds_the_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    kinds = 'import typing\n\nKind: typing.TypeAlias = typing.Literal["edit", "drop"]\n\nk: Kind = "edit"\n'
    root = write_project(tmp_path / "proj", {"pkg/kinds.py": kinds})
    code, _out, err = run(root, _by_symbol("change", symbol="Kind['edit']"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/kinds.py") == kinds.replace('"edit"', '"change"')


@pytest.mark.parametrize(
    "line",
    ['pair: tuple[State, str] = ("old", "old")', 'd: dict[State, str] = {"old": "old"}',
     'pairs: list[tuple[State, str]] = [("old", "old")]'],
    ids=["tuple", "dict", "nested"],
)
def test_a_mixed_display_rewrites_only_the_member_typed_string(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], line: str
) -> None:
    text = f'from typing import Literal\n\nState = Literal["old", "new"]\n\n{line}\n'
    root = write_project(tmp_path / "proj", {"pkg/s.py": text})
    code, _out, err = run(root, _by_symbol("done", symbol="State['old']", rel="pkg/s.py"), monkeypatch, capsys)
    leftover = message("refactor.leftover", path="pkg/s.py", line=5, where="string", old="old")
    assert (code, err) == (0, f"{leftover}\n")
    assert read(root, "pkg/s.py") == text.replace('"old"', '"done"', 2)


LOOPED = """\
from pkg.kinds import DriftKind


def f(kind: DriftKind) -> None:
    print(kind)


def every() -> None:
    for kind in ("edit_model", "drop"):
        f(kind)
"""


def test_a_source_display_already_holding_the_new_value_is_a_name_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/kinds.py": KINDS, "pkg/loop.py": LOOPED})
    before = file_tree(root)
    code, out, err = run(root, _by_symbol("drop"), monkeypatch, capsys)
    assert (code, out) == (1, "")
    conflict = message("refactor.name-conflict", name="drop", path="pkg/loop.py", line=9)
    assert err.splitlines()[-1] == entry_refusal(f"pkg/kinds.py {SYMBOL}", conflict)
    assert file_tree(root) == before
