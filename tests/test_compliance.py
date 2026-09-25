from pathlib import Path

import pytest

from deterministic_refactor.compliance import ALL_CHECKS, check_path, main


def _check(tmp_path: Path, source: str, *, select: tuple[str, ...] = ALL_CHECKS, attr: str | None = None) -> list[str]:
    path = tmp_path / "m.py"
    path.write_text(source)
    return check_path(path, set(select), attr)


def test_untyped_def(tmp_path: Path) -> None:
    [msg] = _check(tmp_path, "def f(a, *args, b, **kw):\n    pass\n", select=("untyped-def",))
    assert "untyped-def: f() missing params a, b, *args, **kw; return" in msg


def test_self_and_cls_exempt(tmp_path: Path) -> None:
    src = "class C:\n    def m(self) -> None: ...\n    @classmethod\n    def k(cls) -> None: ...\n"
    assert _check(tmp_path, src, select=("untyped-def",)) == []


def test_typed_def_clean(tmp_path: Path) -> None:
    assert _check(tmp_path, "def f(a: int) -> int:\n    return a\n", select=("untyped-def",)) == []


def test_unannotated_attr(tmp_path: Path) -> None:
    src = "class C:\n    def __init__(self) -> None:\n        self.x = 1\n"
    [msg] = _check(tmp_path, src, select=("unannotated-attr",))
    assert "unannotated-attr: C.x" in msg


@pytest.mark.parametrize(
    "src",
    [
        "class C:\n    x: int\n    def __init__(self) -> None:\n        self.x = 1\n",
        "class C:\n    def __init__(self) -> None:\n        self.x: int = 1\n",
    ],
)
def test_annotated_attr_clean(tmp_path: Path, src: str) -> None:
    assert _check(tmp_path, src, select=("unannotated-attr",)) == []


def test_mock_check_included(tmp_path: Path) -> None:
    assert len(_check(tmp_path, "Mock()\n", select=("mock",))) == 1


def test_attr_blindspot(tmp_path: Path) -> None:
    src = "def f(o, p: int) -> None:\n    o.name\n    p.name\n"
    [msg] = _check(tmp_path, src, select=(), attr="name")
    assert "attr-blindspot: o.name" in msg


def test_parse_error(tmp_path: Path) -> None:
    [msg] = _check(tmp_path, "def (:\n")
    assert "parse-error" in msg


def test_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = tmp_path / "good.py"
    good.write_text("def f() -> None:\n    pass\n")
    assert main([str(good)]) == 0
    bad = tmp_path / "bad.py"
    bad.write_text("def f():\n    pass\n")
    assert main([str(tmp_path)]) == 1
    assert "bad.py:1" in capsys.readouterr().out
    assert main([]) == 2
    assert main(["--select", "nope", str(good)]) == 2
