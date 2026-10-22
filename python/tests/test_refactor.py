import re
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from rope.refactor import patchedast

from living_architecture.cli import dr_refactor as main
from living_architecture.contract import message
from living_architecture.refactor.rope_refactor import (
    RefactorError,
    _find_symbol_offset,
    _offset_from_line_col,
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "a.py").write_text("def foo() -> int:\n    return 1\n\n\nclass Thing:\n    pass\n")
    (pkg / "b.py").write_text("from pkg.a import foo\n\n\ndef use() -> int:\n    return foo()\n")
    (pkg / "c.py").write_text("")
    (pkg / "sub").mkdir()
    (pkg / "sub" / "__init__.py").write_text("")
    return tmp_path


def _run(project: Path, *args: str) -> int:
    return main(["--project", str(project), *args])


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _rename_foo(project: Path, *flags: str) -> int:
    return _run(project, *flags, "rename", "--file", str(project / "pkg" / "a.py"), "--name", "foo", "--new-name", "bar")


def test_offset_from_line_col() -> None:
    assert _offset_from_line_col("ab\ncd\n", 2, 2) == 4


def test_offset_line_out_of_range() -> None:
    with pytest.raises(RefactorError, match="out of range"):
        _offset_from_line_col("ab\n", 5, 1)


def test_find_symbol_prefers_definition() -> None:
    text = "x = foo\n\ndef foo():\n    pass\n"
    assert text[_find_symbol_offset(text, "foo") :].startswith("foo():")


def test_find_symbol_missing() -> None:
    with pytest.raises(RefactorError, match="not found"):
        _find_symbol_offset("x = 1\n", "foo")


def test_rename_dry_run_writes_nothing(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    before = _tree(project)
    assert _rename_foo(project) == 0
    assert "DRY-RUN. 2 file(s) would change" in capsys.readouterr().out
    assert _tree(project) == before
    assert not (project / ".ropeproject").exists()


def test_rename_apply_changes_only_the_renamed_files(project: Path) -> None:
    before = _tree(project)
    assert _rename_foo(project, "--apply") == 0
    after = _tree(project)
    assert sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k)) == ["pkg/a.py", "pkg/b.py"]
    assert not (project / ".ropeproject").exists()


def test_rename_apply_rewrites_references(project: Path) -> None:
    _run(project, "--apply", "rename", "--file", str(project / "pkg" / "a.py"), "--name", "foo", "--new-name", "bar")
    assert "def bar()" in (project / "pkg" / "a.py").read_text()
    b = (project / "pkg" / "b.py").read_text()
    assert "from pkg.a import bar" in b
    assert "return bar()" in b


def test_rename_by_line_col(project: Path) -> None:
    _run(project, "--apply", "rename", "--file", str(project / "pkg" / "a.py"), "--line", "5", "--col", "7",
         "--new-name", "Other")
    assert "class Other:" in (project / "pkg" / "a.py").read_text()


def test_rename_needs_a_locator(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run(project, "rename", "--file", str(project / "pkg" / "a.py"), "--new-name", "x") == 1
    assert "provide one of" in capsys.readouterr().err


def test_move_symbol(project: Path) -> None:
    _run(project, "--apply", "move-symbol", "--file", str(project / "pkg" / "a.py"), "--name", "foo",
         "--dest", str(project / "pkg" / "c.py"))
    assert "def foo()" in (project / "pkg" / "c.py").read_text()
    assert "def foo()" not in (project / "pkg" / "a.py").read_text()
    b = (project / "pkg" / "b.py").read_text()
    assert "pkg.c.foo()" in b
    assert "pkg.a" not in b


def test_move_module(project: Path) -> None:
    _run(project, "--apply", "move-module", "--module", str(project / "pkg" / "a.py"),
         "--dest", str(project / "pkg" / "sub"))
    assert (project / "pkg" / "sub" / "a.py").is_file()
    assert not (project / "pkg" / "a.py").exists()
    assert "from pkg.sub.a import foo" in (project / "pkg" / "b.py").read_text()


def test_path_outside_project(
    project: Path, tmp_path_factory: pytest.TempPathFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    outside = tmp_path_factory.mktemp("elsewhere") / "x.py"
    outside.write_text("def foo():\n    pass\n")
    assert _run(project, "rename", "--file", str(outside), "--name", "foo", "--new-name", "bar") == 1
    assert "not inside the project" in capsys.readouterr().err


def test_rename_in_file_with_kwonly_string_default(project: Path) -> None:
    # Regression: unpatched rope raises MismatchedTokenError on this signature.
    target = project / "pkg" / "k.py"
    target.write_text('def f(*, m: str = "(host)") -> str:\n    return m\n\n\ndef g() -> str:\n    return f()\n')
    _run(project, "--apply", "rename", "--file", str(target), "--name", "g", "--new-name", "h")
    assert "def h()" in target.read_text()


SCENARIOS = [
    pytest.param(
        "from typing import Annotated\n\n\n"
        "def Field(description: str) -> object:\n    return description\n\n\n"
        'async def probe(p: Annotated[_Payload | None, Field(description="param text")] = None) -> str:\n'
        '    """Docstring text."""\n'
        '    return ""\n',
        "Field",
        "Info",
        ["+def Info(description: str) -> object:",
         '+async def probe(p: Annotated[_Payload | None, Info(description="param text")] = None) -> str:'],
        id="annotated-parameter",
    ),
    pytest.param(
        'def g(*a: object) -> object:\n    return a\n\n\nd = 1\nc = g(f"{d}" "(")\n',
        "g",
        "h",
        ["+def h(*a: object) -> object:", '+c = h(f"{d}" "(")'],
        id="fstring-then-paren-literal",
    ),
    pytest.param(
        "def _admin_rows(*a: object) -> tuple[object]:\n    return (a,)\n\n\n"
        "(checks,) = _admin_rows(\n"
        "    c,\n"
        "    \"SELECT count() FROM system.query_log WHERE type = 'QueryFinish' \"\n"
        "    f\"AND user = '{u.name}' \"\n"
        "    \"AND query LIKE '%getSetting(%readonly%'\",\n"
        ")\n",
        "_admin_rows",
        "admin_rows",
        ["+def admin_rows(*a: object) -> tuple[object]:", "+(checks,) = admin_rows("],
        id="fstring-clickhouse",
    ),
    pytest.param(
        'M = type\n\n\nclass A(B, metaclass=M, x=")"):\n    pass\n\n\n'
        'try:\n    a = 1\nexcept E:\n    b = 2\nelse:\n    c = M("(")\nfinally:\n    d = ")"\n',
        "M",
        "N",
        ["+N = type", '+class A(B, metaclass=N, x=")"):', '+    c = N("(")'],
        id="class-keywords-and-try-else-finally",
    ),
    pytest.param(
        'def h() -> None:\n    a = 1\n    f(t"{a}(", ")")\n',
        "a",
        "b",
        ["+    b = 1", '+    f(t"{b}(", ")")'],
        id="tstring",
        marks=pytest.mark.skipif(sys.version_info < (3, 14), reason="t-strings"),
    ),
    pytest.param(
        'def f(s: str = "😀", p: A[F(d="(")] = None) -> str:\n    return str(p)\n',
        "p",
        "q",
        ['+def f(s: str = "😀", q: A[F(d="(")] = None) -> str:', "+    return str(q)"],
        id="non-ascii-before-annotation",
    ),
]


@pytest.mark.parametrize(("source", "name", "new_name", "added"), SCENARIOS)
def test_rename_walks_every_construct(
    project: Path, capsys: pytest.CaptureFixture[str], source: str, name: str, new_name: str, added: list[str]
) -> None:
    target = project / "pkg" / "m.py"
    target.write_text(source, encoding="utf-8")
    assert _run(project, "rename", "--file", str(target), "--name", name, "--new-name", new_name) == 0
    out = capsys.readouterr().out.splitlines()
    for line in added:
        assert line in out


def _gap_refused(project: Path, capsys: pytest.CaptureFixture[str], line: int, *flags: str) -> None:
    before = _tree(project)
    assert _rename_foo(project, *flags) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == message("refactor.rope-walk", path="pkg/gap.py", line=line) + "\n"
    assert _tree(project) == before


@pytest.mark.parametrize("flags", [(), ("--apply",)], ids=["dry-run", "apply"])
def test_walker_crash_is_refused_at_the_construct(
    project: Path,
    capsys: pytest.CaptureFixture[str],
    restore_rope_visitor: Callable[[str], None],
    annotation_gap: str,
    flags: tuple[str, ...],
) -> None:
    restore_rope_visitor("_arg")
    (project / "pkg" / "gap.py").write_text(annotation_gap)
    _gap_refused(project, capsys, 3, *flags)


def test_silent_walker_gap_is_refused(
    project: Path, capsys: pytest.CaptureFixture[str], restore_rope_visitor: Callable[[str], None]
) -> None:
    restore_rope_visitor("_JoinedStr")
    # rope walks a module only to place offsets among its inner scopes, so the gap sits in a function.
    (project / "pkg" / "gap.py").write_text('from pkg.a import foo\n\n\ndef use() -> None:\n    x = foo()\n    y = f"{x}" "z"\n')
    _gap_refused(project, capsys, 6)


def test_exception_inside_ropes_walker_is_a_gap(
    project: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A string pattern that never matches makes rope's _consume_pattern raise AttributeError.
    monkeypatch.setattr(patchedast._Source, "_string_pattern", re.compile("(?!)"))
    (project / "pkg" / "gap.py").write_text('from pkg.a import foo\n\n\ndef use() -> str:\n    foo()\n    return "x"\n')
    _gap_refused(project, capsys, 4)


def test_value_error_inside_ropes_walker_is_a_gap(
    project: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def unmatched(self: patchedast._PatchingASTWalker, node: object) -> None:
        self._handle(node, ["\x00"])  # rope's consume_joined_string raises ValueError

    monkeypatch.setattr(patchedast._PatchingASTWalker, "_JoinedStr", unmatched)
    (project / "pkg" / "gap.py").write_text('from pkg.a import foo\n\n\ndef use() -> None:\n    x = foo()\n    y = f"{x}"\n')
    _gap_refused(project, capsys, 4)


def test_exception_outside_ropes_walker_propagates(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(self: object, node: object) -> None:
        raise AttributeError("not a walker gap")

    monkeypatch.setattr(patchedast._PatchingASTWalker, "_Name", broken)
    with pytest.raises(AttributeError, match="not a walker gap"):
        _rename_foo(project)
