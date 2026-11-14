"""Python `dr-compliance --attr`: receivers basedpyright types as Unknown or Any."""

from __future__ import annotations

from pathlib import Path

import pytest

from living_architecture.cli import dr_compliance
from living_architecture.contract import message

UNTYPED = """\
from typing import Any

from missing_lib import untyped_call


class Model:
    formula: str = ""


def f(*, measures: list) -> list[object]:
    return [m.formula for m in measures]


def k() -> None:
    mdl = untyped_call()
    print(mdl.formula)
    hops = []
    print(list(map(lambda h: h.formula, hops)))


def g(o: Any) -> object:
    return o.formula


def typed(x: Model, xs: list[Model]) -> list[str]:
    return [x.formula, *(i.formula for i in xs)]
"""

UNIONS = """\
from typing import Any

from missing_lib import thing


class Model:
    formula: str = ""


def u(x: Model | int, y: list, w: Model | Any) -> None:
    z = x if isinstance(x, Model) else y[0]
    print(z.formula, w.formula)
    print(y[
        0
    ].formula)
    print(thing.a.formula)
"""


def _blindspot(path: str, line: int, receiver: str, kind: str) -> str:
    return message("compliance.attr-blindspot", path=path, line=line, receiver=receiver, attr="formula", type=kind)


@pytest.fixture
def cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _attr(*paths: str) -> int:
    return dr_compliance(["--select", "", "--attr", "formula", *paths])


def test_receivers_the_checker_cannot_type(cwd: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (cwd / "m.py").write_text(UNTYPED, encoding="utf-8")
    assert _attr("m.py") == 1
    assert capsys.readouterr().out.splitlines() == [
        _blindspot("m.py", 11, "m", "Unknown"),
        _blindspot("m.py", 16, "mdl", "Unknown"),
        _blindspot("m.py", 18, "h", "Unknown"),
        _blindspot("m.py", 22, "o", "Any"),
    ]


def test_typed_receivers_are_clean(cwd: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (cwd / "m.py").write_text(UNTYPED.split("def f(")[0] + UNTYPED.split("\n\n\n")[-1], encoding="utf-8")
    assert _attr("m.py") == 0
    assert capsys.readouterr().out == ""


def test_unions_multiline_and_chained_receivers(cwd: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (cwd / "u.py").write_text(UNIONS, encoding="utf-8")
    assert _attr("u.py") == 1
    assert capsys.readouterr().out.splitlines() == [
        _blindspot("u.py", 12, "z", "Unknown"),
        _blindspot("u.py", 12, "w", "Any"),
        _blindspot("u.py", 13, "y[ 0 ]", "Unknown"),
        _blindspot("u.py", 16, "thing.a", "Unknown"),
    ]


def test_expression_receivers_report_only_their_own_unknown_or_any(
    cwd: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (cwd / "m.py").write_text(
        "from typing import Any\n\n\n"
        "class Loose:\n"
        "    formula: Any = None\n\n\n"
        "class Strict:\n"
        '    formula: str = ""\n\n\n'
        "def make() -> Loose:\n"
        "    return Loose()\n\n\n"
        "def f(loose: list[Loose], mixed: list[Strict | Any], untyped: list) -> None:\n"
        "    print(loose[0].formula, make().formula)\n"
        "    print(mixed[0].formula, untyped[0].formula)\n",
        encoding="utf-8",
    )
    assert _attr("m.py") == 1
    assert capsys.readouterr().out.splitlines() == [
        _blindspot("m.py", 18, "mixed[0]", "Any"),
        _blindspot("m.py", 18, "untyped[0]", "Unknown"),
    ]


def test_findings_follow_the_given_file_order(cwd: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (cwd / "b.py").write_text("def f(o) -> object:\n    return o.formula\n", encoding="utf-8")
    (cwd / "a.py").write_text("def f(o) -> object:\n    return o.formula\n", encoding="utf-8")
    assert _attr("b.py", "a.py") == 1
    assert capsys.readouterr().out.splitlines() == [
        _blindspot("b.py", 2, "o", "Unknown"),
        _blindspot("a.py", 2, "o", "Unknown"),
    ]


def test_unknown_wins_over_any_in_one_receiver(cwd: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (cwd / "m.py").write_text(
        "from typing import Any\n\n\n"
        "def f(a: Any, b: list, c: bool) -> object:\n"
        "    x = a if c else b[0]\n"
        "    return x.formula\n",
        encoding="utf-8",
    )
    assert _attr("m.py") == 1
    assert capsys.readouterr().out.splitlines() == [_blindspot("m.py", 6, "x", "Unknown")]


def test_one_finding_per_access_position(cwd: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (cwd / "m.py").write_text("def f(o) -> object:\n    return o.formula\n", encoding="utf-8")
    assert _attr("m.py", "m.py") == 1
    assert capsys.readouterr().out.splitlines() == [_blindspot("m.py", 2, "o", "Unknown")]


def test_blindspots_merge_into_each_files_line_order(cwd: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (cwd / "a.py").write_text("def f(o) -> object:\n    return o.formula\n\n\ndef g(x): ...\n", encoding="utf-8")
    (cwd / "b.py").write_text("def h(x): ...\n", encoding="utf-8")
    assert dr_compliance(["--select", "untyped-def", "--attr", "formula", "a.py", "b.py"]) == 1
    assert [line.split(": ")[0] for line in capsys.readouterr().out.splitlines()] == ["a.py:1", "a.py:2", "a.py:5", "b.py:1"]


def test_language_server_failure_exits_2(
    cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (cwd / "m.py").write_text(UNTYPED, encoding="utf-8")
    monkeypatch.setenv("NODE_OPTIONS", "--require /nonexistent.js")
    assert _attr("m.py") == 2
    assert capsys.readouterr() == ("", message("compliance.pyright-failed", attr="formula") + "\n")


def test_language_server_starts_only_with_attr(
    cwd: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (cwd / "m.py").write_text("def f() -> None:\n    pass\n", encoding="utf-8")
    monkeypatch.setenv("NODE_OPTIONS", "--require /nonexistent.js")
    assert dr_compliance(["m.py"]) == 0
    assert capsys.readouterr() == ("", "")
