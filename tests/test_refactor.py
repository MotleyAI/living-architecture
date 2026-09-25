from pathlib import Path

import pytest

from deterministic_refactor.refactor import _find_symbol_offset, _offset_from_line_col, main


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


def _run(project: Path, *args: str) -> None:
    main(["--project", str(project), *args])


def test_offset_from_line_col() -> None:
    assert _offset_from_line_col("ab\ncd\n", 2, 2) == 4


def test_offset_line_out_of_range() -> None:
    with pytest.raises(SystemExit, match="out of range"):
        _offset_from_line_col("ab\n", 5, 1)


def test_find_symbol_prefers_definition() -> None:
    text = "x = foo\n\ndef foo():\n    pass\n"
    assert text[_find_symbol_offset(text, "foo") :].startswith("foo():")


def test_find_symbol_missing() -> None:
    with pytest.raises(SystemExit, match="not found"):
        _find_symbol_offset("x = 1\n", "foo")


def test_rename_dry_run_writes_nothing(project: Path, capsys: pytest.CaptureFixture[str]) -> None:
    before = (project / "pkg" / "b.py").read_text()
    _run(project, "rename", "--file", str(project / "pkg" / "a.py"), "--name", "foo", "--new-name", "bar")
    assert "DRY-RUN. 2 file(s) would change" in capsys.readouterr().out
    assert (project / "pkg" / "b.py").read_text() == before


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


def test_rename_needs_a_locator(project: Path) -> None:
    with pytest.raises(SystemExit, match="provide one of"):
        _run(project, "rename", "--file", str(project / "pkg" / "a.py"), "--new-name", "x")


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


def test_path_outside_project(project: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    outside = tmp_path_factory.mktemp("elsewhere") / "x.py"
    outside.write_text("def foo():\n    pass\n")
    with pytest.raises(SystemExit, match="not inside the project"):
        _run(project, "rename", "--file", str(outside), "--name", "foo", "--new-name", "bar")


def test_rename_in_file_with_kwonly_string_default(project: Path) -> None:
    # Regression: unpatched rope raises MismatchedTokenError on this signature.
    target = project / "pkg" / "k.py"
    target.write_text('def f(*, m: str = "(host)") -> str:\n    return m\n\n\ndef g() -> str:\n    return f()\n')
    _run(project, "--apply", "rename", "--file", str(target), "--name", "g", "--new-name", "h")
    assert "def h()" in target.read_text()
