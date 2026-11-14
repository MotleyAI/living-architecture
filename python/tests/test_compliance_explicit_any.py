import subprocess
import sys
from pathlib import Path

import pytest

from living_architecture.cli import dr_compliance as main
from living_architecture.contract import message
from living_architecture.refactor.compliance import ALL_CHECKS, check_path


def _src(*lines: str) -> str:
    """One source line per argument, so a line's number is its position."""
    return "\n".join(lines) + "\n"


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _finding(path: Path, line: int) -> str:
    return message("compliance.explicit-any", path=str(path), line=line, any="Any", top="object")


def _lines(root: Path, target: str = "m.py") -> list[int]:
    """The lines of `target`'s explicit-any findings, each checked to be the finding's exact text."""
    path = root / target
    found = check_path(path, {"explicit-any"}, None)
    lines = sorted(int(f.removeprefix(f"{path}:").split(":", 1)[0]) for f in found)
    assert sorted(found) == sorted(_finding(path, n) for n in lines)
    return lines


def _check(root: Path, source: str) -> list[int]:
    _write(root, {"m.py": source})
    return _lines(root)


def test_nested_and_variadic_annotations(tmp_path: Path) -> None:
    path = tmp_path / "m.py"
    path.write_text(_src("from typing import Any", "def f(a: dict[str, Any], **kw: Any) -> list[Any]: ..."))
    expected = f"{path}:2: explicit-any: an `Any` type — use a real type or `object`"
    assert check_path(path, {"explicit-any"}, None) == [expected] * 3


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (_src("from typing import Any", "def f(a: int, /, b: Any, *args: Any, c: Any, **kw: Any) -> Any: ..."), [2] * 5),
        (_src("from typing import Any", "async def f() -> Any: ..."), [2]),
        (_src("from typing import Any, Callable", "x: Callable[[Any], dict[str, list[Any]]]"), [2, 2]),
        (_src("from typing import Any", "x: Any | None = None"), [2]),
        (_src("from typing import Any", "class C:", "    x: Any", "    def m(self) -> 'C | Any': ..."), [3, 4]),
    ],
)
def test_annotation_sites(tmp_path: Path, source: str, expected: list[int]) -> None:
    assert _check(tmp_path, source) == expected


def test_every_spelling(tmp_path: Path) -> None:
    source = _src(
        "from typing import Any",
        "from typing import Any as X",
        "import typing as t",
        "import typing",
        "import typing_extensions",
        "a: Any",
        "b: X",
        "c: t.Any",
        "d: typing.Any",
        "e: typing_extensions.Any",
    )
    assert _check(tmp_path, source) == [6, 7, 8, 9, 10]


@pytest.mark.parametrize(
    ("header", "use"),
    [
        ("from typing import *", "Any"),
        ("from typing_extensions import *", "Any"),
        ("from typing_extensions import Any", "Any"),
        ("import typing_extensions as te", "te.Any"),
    ],
)
def test_other_spellings(tmp_path: Path, header: str, use: str) -> None:
    assert _check(tmp_path, _src(header, f"x: {use}")) == [2]


def test_expressions_outside_annotations(tmp_path: Path) -> None:
    source = _src(
        "from typing import Any, Generic, TypeVar, cast",
        'T = TypeVar("T", bound=Any)',
        "class Base(Generic[T]): ...",
        "class C(Base[Any]): ...",
        "Alias = dict[str, Any]",
        "y = cast(Any, 1)",
        "z = list[Any]()",
        "print(Any)",
    )
    assert _check(tmp_path, source) == [2, 4, 5, 6, 7, 8]


def test_aliases_are_not_followed(tmp_path: Path) -> None:
    assert _check(tmp_path, _src("from typing import Any", "", "A = Any", "x: A")) == [3]


def test_forward_references_and_type_comments(tmp_path: Path) -> None:
    source = _src(
        "from typing import Any",
        'x: "dict[str, Any]"',
        'y: list["Any"]',
        "z = []  # type: list[Any]",
        "def f(a, b):",
        "    # type: (Any, int) -> Any",
        "    return a",
        "def g(a: \"Any\") -> \"list['Any']\": ...",
    )
    assert _check(tmp_path, source) == [2, 3, 4, 6, 6, 8, 8]


def test_argument_and_statement_type_comments(tmp_path: Path) -> None:
    source = _src(
        "from typing import Any",
        "def f(",
        "    a,  # type: Any",
        "    b,  # type: int",
        "):",
        "    # type: (...) -> None",
        "    pass",
        "for v in []:  # type: Any",
        "    pass",
        'with open("f") as h:  # type: Any',
        "    pass",
    )
    assert _check(tmp_path, source) == [3, 8, 10]


def test_strings_that_are_not_forward_references(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _src(
        "from typing import Annotated, Any, Literal",
        'x: Literal["Any"]',
        'y: Annotated[int, "Any"]',
        "z = 1  # type: ignore",
        "w = []  # type: list[Any",
        'v = "Any"',
        'u: Annotated["Any", "Any"]',
        "q = []  # type: ignore[assignment]",
    )
    assert _check(tmp_path, source) == [7]
    assert main(["--select", "explicit-any", str(tmp_path / "m.py")]) == 1
    assert capsys.readouterr().err == ""


def test_misplaced_type_comment_is_skipped(tmp_path: Path) -> None:
    source = _src("from typing import Any", "x = [", "    1,  # type: int", "]", "y: Any")
    _write(tmp_path, {"m.py": source})
    assert check_path(tmp_path / "m.py", set(ALL_CHECKS), None) == [_finding(tmp_path / "m.py", 5)]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (_src("from typing import Any", "def f(Any: int) -> None:", "    x: Any = 1", "y: Any"), [4]),
        (_src("from typing import Any", "def f(Any: Any) -> Any:", "    x: Any = 1"), [2, 2]),
        (_src("from typing import Any", "def f() -> None:", "    Any = int", "    x: Any = 1", "y: Any"), [5]),
        (_src("from typing import Any", "Any = object", "x: Any", "import typing", "y: typing.Any"), [5]),
        (_src("from typing import Any", "x: Any", "Any = object", "import typing", "y: typing.Any"), [5]),
        (_src("import typing as t", "import typing", "t = None", "x: t.Any", "y: typing.Any"), [5]),
    ],
)
def test_shadowed_and_mixed_bindings(tmp_path: Path, source: str, expected: list[int]) -> None:
    assert _check(tmp_path, source) == expected


@pytest.mark.parametrize(
    "binding",
    [
        "for Any in []:\n    pass",
        'with open("f") as Any:\n    pass',
        "(Any := 1)",
        "def Any() -> None: ...",
        "class Any: ...",
        "import os as Any",
        "from os import path as Any",
        "Any: int = 1",
        "def g() -> None:\n    global Any\n    Any = int",
        "try:\n    pass\nexcept Exception as Any:\n    pass",
        "match 1:\n    case Any:\n        pass",
        "match []:\n    case [*Any]:\n        pass",
        "match {}:\n    case {**Any}:\n        pass",
        "match 1:\n    case int() as Any:\n        pass",
    ],
)
def test_any_other_module_binding_leaves_it_unreported(tmp_path: Path, binding: str) -> None:
    source = _src("from typing import Any", "import typing", "x: Any", "y: typing.Any", binding)
    assert _check(tmp_path, source) == [4]


def test_class_scope(tmp_path: Path) -> None:
    source = _src(
        "class C:",
        "    from typing import Any",
        "    @register(Any)",
        "    def m(self, x: Any) -> None:",
        "        y: Any = x",
        "    z: Any",
    )
    assert _check(tmp_path, source) == [3, 4, 6]


def test_global(tmp_path: Path) -> None:
    source = _src(
        "from typing import Any",
        "def f() -> None:",
        "    global Any",
        "    x: Any = 1",
    )
    assert _check(tmp_path, source) == [4]


def test_global_import_binds_the_module_name(tmp_path: Path) -> None:
    source = _src(
        "def f() -> None:",
        "    global Any",
        "    from typing import Any",
        "    x: Any = 1",
        "y: Any",
    )
    assert _check(tmp_path, source) == [4, 5]


def test_nonlocal_and_closures(tmp_path: Path) -> None:
    source = _src(
        "def outer() -> None:",
        "    from typing import Any",
        "    def inner(p: Any) -> None:",
        "        nonlocal Any",
        "        x: Any = p",
        "    y: Any = 2",
        "def outer2() -> None:",
        "    Any = int",
        "    def inner2() -> None:",
        "        nonlocal Any",
        "        from typing import Any",
        "        z: Any = 1",
        "    w: Any = 2",
    )
    assert _check(tmp_path, source) == [3, 5, 6]


def test_comprehension_bindings(tmp_path: Path) -> None:
    source = _src(
        "from typing import Any",
        "a = [Any for Any in range(3)]",
        "b = [Any for _ in range(3)]",
        "c = [0 for Any in Any]",
    )
    assert _check(tmp_path, source) == [3, 4]


def test_try_except_import_error(tmp_path: Path) -> None:
    source = _src(
        "try:",
        "    from typing_extensions import Any",
        "except ImportError:",
        "    from typing import Any",
        "x: Any",
    )
    assert _check(tmp_path, source) == [5]


def test_first_party_re_exports(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "pkg/__init__.py": "from .compat import *\n",
            "pkg/compat.py": "from typing import Any as Any\n",
            "pkg/a.py": _src(
                "from pkg.compat import Any",
                "from pkg import Any as X",
                "import pkg.compat as c",
                "a: Any",
                "b: X",
                "d: c.Any",
            ),
        },
    )
    assert _lines(tmp_path, "pkg/a.py") == [4, 5, 6]
    assert _lines(tmp_path, "pkg/compat.py") == []
    assert _lines(tmp_path, "pkg/__init__.py") == []


def test_relative_and_chained_re_exports(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/compat.py": "from typing import Any as Any\n",
            "pkg/compat2.py": "from pkg.compat import Any\n",
            "pkg/other.py": "Any = object\n",
            "pkg/sub/__init__.py": "from typing import Any\n",
            "pkg/sub/m.py": _src(
                "from ..compat import Any",
                "from ..compat2 import Any as B",
                "from pkg.sub import Any as C",
                "from . import Any as D",
                "a: Any",
                "b: B",
                "c: C",
                "d: D",
                "from pkg.other import Any as E",
                "from .missing import Any as F",
                "from pkg.compat import Missing as G",
                "e: E",
                "f: F",
                "g: G",
            ),
        },
    )
    assert _lines(tmp_path, "pkg/sub/m.py") == [5, 6, 7, 8]


def test_star_import_honours_all_and_private_names(tmp_path: Path) -> None:
    both = _src("from typing import Any", "from typing import Any as _Any")
    uses = _src("a: Any", "b: _Any")
    _write(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/compat.py": both + '__all__ = ["_Any"]\n',
            "pkg/plain.py": both,
            "pkg/a.py": "from pkg.compat import *\n" + uses,
            "pkg/b.py": "from pkg.plain import *\n" + uses,
        },
    )
    assert _lines(tmp_path, "pkg/a.py") == [3]
    assert _lines(tmp_path, "pkg/b.py") == [2]


def test_re_export_cycle_ends_unresolved(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/a.py": _src("from pkg.b import Any", "x: Any"),
            "pkg/b.py": _src("from pkg.a import Any", "y: Any"),
            "pkg/c.py": _src("from pkg.d import *", "z: Any"),
            "pkg/d.py": "from pkg.c import *\n",
            "pkg/e.py": _src("from typing import Any", "w: Any"),
        },
    )
    files = [str(tmp_path / "pkg" / name) for name in ("a.py", "b.py", "c.py", "d.py", "e.py")]
    script = "import sys; from living_architecture.cli import dr_compliance; sys.exit(dr_compliance(sys.argv[1:]))"
    run = subprocess.run(
        [sys.executable, "-c", script, "--select", "explicit-any", *files],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert (run.returncode, run.stdout, run.stderr) == (1, _finding(tmp_path / "pkg" / "e.py", 2) + "\n", "")


def test_modules_that_are_not_first_party(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "typing.py": "Any = int\n",
            "m.py": _src(
                "from pydantic import Any",
                "from not_a_module import Any as Y",
                "from typing import Any as Z",
                "import typing",
                "a: Any",
                "b: Y",
                "c: Z",
                "d: typing.Any",
            ),
        },
    )
    assert _lines(tmp_path) == [7, 8]


def test_src_layout_and_directory_without_init(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "src/pkg/__init__.py": "",
            "src/pkg/util/compat.py": "from typing import Any as Any\n",
            "src/pkg/a.py": _src("from pkg.util.compat import Any", "x: Any"),
            "src/pkg/sub/__init__.py": "",
            "src/pkg/sub/m.py": _src("from pkg.util.compat import Any", "y: Any"),
        },
    )
    assert _lines(tmp_path, "src/pkg/a.py") == [2]
    assert _lines(tmp_path, "src/pkg/sub/m.py") == [2]


def test_flat_layout(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "flat/helpers.py": "from typing import Any as Any\n",
            "flat/m.py": _src("from helpers import Any", "x: Any"),
        },
    )
    assert _lines(tmp_path, "flat/m.py") == [2]


def test_parse_error_only(tmp_path: Path) -> None:
    _write(tmp_path, {"m.py": _src("from typing import Any", "x: Any = (")})
    [msg] = check_path(tmp_path / "m.py", set(ALL_CHECKS), None)
    assert "parse-error" in msg


def test_default_run_reports_any(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "m.py"
    path.write_text(_src("from typing import Any", "", "", "def f(x: Any) -> None:", "    pass"))
    assert main([str(path)]) == 1
    assert capsys.readouterr().out == _finding(path, 4) + "\n"
