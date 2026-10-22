from collections.abc import Callable
from pathlib import Path

import pytest

from living_architecture.cli import dr_compliance as main
from living_architecture.contract import message
from living_architecture.refactor.compliance import ALL_CHECKS, check_path


def _check(tmp_path: Path, source: str, *, select: tuple[str, ...] = ALL_CHECKS, attr: str | None = None) -> list[str]:
    path = tmp_path / "m.py"
    path.write_text(source, encoding="utf-8")
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
    assert main(["--select", "nope", str(good)]) == 2


def test_main_without_paths_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_rope_walk_is_a_default_check() -> None:
    assert ALL_CHECKS == ("untyped-def", "unannotated-attr", "mock", "rope-walk")


def test_rope_walk_clean_file(tmp_path: Path) -> None:
    src = (
        'async def probe(p: Annotated[_Payload | None, Field(description="param text")] = None) -> str:\n'
        '    return g(f"{p}" "(")\n'
        'class A(B, metaclass=M, x=")"):\n    y = rb"("\n'
    )
    assert _check(tmp_path, src, select=("rope-walk",)) == []


def test_rope_walk_gap_reported_at_the_construct(
    tmp_path: Path, restore_rope_visitor: Callable[[str], None], annotation_gap: str
) -> None:
    restore_rope_visitor("_arg")
    assert _check(tmp_path, annotation_gap, select=("rope-walk",)) == [
        message("compliance.rope-walk", path=str(tmp_path / "m.py"), line=3)
    ]


def test_rope_walk_parse_error_only(tmp_path: Path) -> None:
    [msg] = _check(tmp_path, "def (:\n", select=("rope-walk",))
    assert "parse-error" in msg


def test_rope_walk_lists_only_the_uncoverable_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    restore_rope_visitor: Callable[[str], None],
    annotation_gap: str,
) -> None:
    restore_rope_visitor("_arg")
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "a.py").write_text(annotation_gap)
    (pkg / "b.py").write_text("x = 1\n")  # an annotation would be a gap under rope's own `_arg`
    gap = message("compliance.rope-walk", path=str(pkg / "a.py"), line=3)
    assert main(["--select", "rope-walk", str(pkg / "a.py"), str(pkg / "b.py")]) == 1
    assert capsys.readouterr().out == gap + "\n"
    assert main([str(pkg / "a.py")]) == 1
    assert gap in capsys.readouterr().out.splitlines()
