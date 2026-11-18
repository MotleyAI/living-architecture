"""The literal sources of a name: the string literals a once-bound name, constant or loop target holds, followed
through assignments, imports and re-exports of the project's own modules."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from deterministic_refactor.refactor import literal_sources
from deterministic_refactor.refactor.patch_targets import SourceFolders
from deterministic_refactor.refactor.static_resolver import Resolver

# A literal as (file, its text with quotes, which occurrence of that text in the file).
Quoted = tuple[str, str, int]
Found = tuple[str, int, int, str]

USE = "pkg/use.py"
A = {"pkg/a.py": 'A = "columns"\n'}
SECTIONS = {"pkg/a.py": 'SECTIONS = ("columns", "name")\n'}
K = {"pkg/k.py": 'class K:\n    NAME = "columns"\n'}


def _in_function(*body: str) -> str:
    return "def f(c: bool, p: str) -> None:\n" + "".join(f"    {line}\n" for line in body)


def _found(root: Path, files: dict[str, str], read: str) -> list[Found]:
    """The sources of the one load of `read` in `pkg/use.py`, as (file, line, column, value)."""
    for rel, text in {"pkg/__init__.py": "", **files}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    resolver = Resolver(SourceFolders([root]))
    module = resolver.load("pkg.use")
    assert module is not None
    [(expr, scope)] = [(e, s) for e, s in module.binder.loads if ast.unparse(e) == read]
    found = literal_sources.literal_sources(resolver, module, scope, expr)
    return sorted((s.path.relative_to(root).as_posix(), s.line, s.col, s.value) for s in found)


def _expected(files: dict[str, str], literals: list[Quoted]) -> list[Found]:
    out: list[Found] = []
    for rel, quoted, nth in literals:
        text = files[rel]
        offset = -1
        for _ in range(nth + 1):
            offset = text.index(quoted, offset + 1)
        line_start = text.rfind("\n", 0, offset) + 1
        out.append((rel, text.count("\n", 0, offset) + 1, offset - line_start, quoted[1:-1]))
    return sorted(out)


def _check(tmp_path: Path, files: dict[str, str], read: str, literals: list[Quoted]) -> None:
    for text in files.values():
        ast.parse(text)
    assert _found(tmp_path.resolve(), files, read) == _expected(files, literals)


@pytest.mark.parametrize(
    ("use", "read", "literals"),
    [
        pytest.param(_in_function('s = "columns"', "print(s)"), "s", [(USE, '"columns"', 0)], id="local"),
        pytest.param(_in_function("s = 'columns'", "print(s)"), "s", [(USE, "'columns'", 0)], id="single-quoted"),
        pytest.param(_in_function('s: str = "columns"', "print(s)"), "s", [(USE, '"columns"', 0)], id="annotated-local"),
        pytest.param('NAME = "columns"\n\n\n' + _in_function("print(NAME)"), "NAME", [(USE, '"columns"', 0)],
                     id="module-constant"),
        pytest.param('NAME = "columns"\nprint(NAME)\n', "NAME", [(USE, '"columns"', 0)], id="module-constant-read-beside-it"),
        pytest.param('from typing import Final\n\nNAME: Final = "columns"\n\n\n' + _in_function("print(NAME)"), "NAME",
                     [(USE, '"columns"', 0)], id="annotated-module-constant"),
        pytest.param('class K:\n    NAME = "columns"\n\n\n' + _in_function("print(K.NAME)"), "K.NAME",
                     [(USE, '"columns"', 0)], id="class-constant"),
        pytest.param('class K:\n    NAME: str = "columns"\n\n\n' + _in_function("print(K.NAME)"), "K.NAME",
                     [(USE, '"columns"', 0)], id="annotated-class-constant"),
    ],
)
def test_a_once_bound_name_holds_the_literal_assigned_to_it(
    tmp_path: Path, use: str, read: str, literals: list[Quoted]
) -> None:
    _check(tmp_path, {USE: use}, read, literals)


BOTH = [(USE, '"columns"', 0), (USE, '"name"', 0)]


@pytest.mark.parametrize(
    ("use", "literals"),
    [
        pytest.param(_in_function('for s in ("columns", "name"):', "    print(s)"), BOTH, id="for-over-a-tuple"),
        pytest.param(_in_function('for s in ["columns", "name"]:', "    print(s)"), BOTH, id="for-over-a-list"),
        pytest.param(_in_function('for s in {"columns", "name"}:', "    print(s)"), BOTH, id="for-over-a-set"),
        pytest.param(_in_function('xs = ("columns", "name")', "for s in xs:", "    print(s)"), BOTH,
                     id="for-over-a-local-holding-a-tuple"),
        pytest.param('XS = ["columns", "name"]\n\n\n' + _in_function("for s in XS:", "    print(s)"), BOTH,
                     id="for-over-a-module-constant-holding-a-list"),
        pytest.param('XS = {"columns", "name"}\nfor s in XS:\n    print(s)\n', BOTH, id="module-level-for-over-a-set"),
        pytest.param(_in_function('print([str(s) for s in ("columns", "name")])'), BOTH, id="comprehension-over-a-tuple"),
        pytest.param('XS = ("columns", "name")\n\n\n' + _in_function("print({s: 1 for s in XS})"), BOTH,
                     id="dict-comprehension-over-a-module-constant"),
        pytest.param(_in_function('xs = ["columns", "name"]', "print(list(str(s) for s in xs))"), BOTH,
                     id="generator-over-a-local"),
    ],
)
def test_a_loop_target_holds_every_element_of_the_display(tmp_path: Path, use: str, literals: list[Quoted]) -> None:
    _check(tmp_path, {USE: use}, "s", literals)


@pytest.mark.parametrize(
    ("files", "read", "literals"),
    [
        pytest.param({USE: _in_function('a = "columns"', "b = a", "print(b)")}, "b", [(USE, '"columns"', 0)],
                     id="local-chain"),
        pytest.param({USE: 'NAME = "columns"\n\n\n' + _in_function("s = NAME", "print(s)")}, "s", [(USE, '"columns"', 0)],
                     id="local-from-a-module-constant"),
        pytest.param({USE: _in_function('for s in ("columns", "name"):', "    t = s", "    print(t)")}, "t", BOTH,
                     id="local-from-a-loop-target"),
        pytest.param({**A, USE: "from pkg.a import A\n\nprint(A)\n"}, "A", [("pkg/a.py", '"columns"', 0)], id="import"),
        pytest.param({**A, USE: "from pkg.a import A as B\n\nprint(B)\n"}, "B", [("pkg/a.py", '"columns"', 0)],
                     id="aliased-import"),
        pytest.param({**A, USE: "from .a import A\n\nprint(A)\n"}, "A", [("pkg/a.py", '"columns"', 0)],
                     id="relative-import"),
        pytest.param({**A, "pkg/b.py": "from pkg.a import A\n\nB = A\n", USE: "from pkg.b import B\n\nprint(B)\n"}, "B",
                     [("pkg/a.py", '"columns"', 0)], id="assignment-of-an-import"),
        pytest.param({**A, "pkg/__init__.py": "from pkg.a import A\n", USE: "from pkg import A\n\nprint(A)\n"}, "A",
                     [("pkg/a.py", '"columns"', 0)], id="re-export"),
        pytest.param({**K, USE: "from pkg.k import K\n\nprint(K.NAME)\n"}, "K.NAME", [("pkg/k.py", '"columns"', 0)],
                     id="constant-of-an-imported-class"),
    ],
)
def test_sources_follow_assignments_imports_and_re_exports(
    tmp_path: Path, files: dict[str, str], read: str, literals: list[Quoted]
) -> None:
    _check(tmp_path, files, read, literals)


@pytest.mark.parametrize(
    "files",
    [
        pytest.param({**SECTIONS, USE: "from pkg.a import SECTIONS\n\nfor s in SECTIONS:\n    print(s)\n"}, id="import"),
        pytest.param({**SECTIONS, USE: "from pkg.a import SECTIONS\n\nNAMES = SECTIONS\nprint([str(s) for s in NAMES])\n"},
                     id="assignment-of-an-import"),
    ],
)
def test_a_loop_follows_the_name_it_iterates_to_its_display(tmp_path: Path, files: dict[str, str]) -> None:
    _check(tmp_path, files, "s", [("pkg/a.py", '"columns"', 0), ("pkg/a.py", '"name"', 0)])


@pytest.mark.parametrize(
    ("use", "read"),
    [
        pytest.param('def f(s: str = "columns") -> None:\n    print(s)\n', "s", id="parameter"),
        pytest.param(_in_function('s = "columns" if c else "name"', "print(s)"), "s", id="conditional-value"),
        pytest.param(_in_function('s = "col" + "umns"', "print(s)"), "s", id="computed-value"),
        pytest.param(_in_function('s = str("columns")', "print(s)"), "s", id="call-value"),
        pytest.param(_in_function('s = f"columns"', "print(s)"), "s", id="f-string"),
        pytest.param(_in_function('s = "col" "umns"', "print(s)"), "s", id="implicit-concatenation"),
        pytest.param(_in_function('k = "drop"', 'k = "columns"', "print(k)"), "k", id="second-binding"),
        pytest.param(_in_function("if c:", '    s = "columns"', "else:", '    s = "name"', "print(s)"), "s",
                     id="bound-in-both-branches"),
        pytest.param('import sys\n\nif sys.argv:\n    NAME = "columns"\nelse:\n    NAME = "name"\nprint(NAME)\n', "NAME",
                     id="module-constant-bound-in-both-branches"),
        pytest.param('class K:\n    NAME = "columns"\n    NAME = "name"\n\n\nprint(K.NAME)\n', "K.NAME",
                     id="class-constant-bound-twice"),
        pytest.param(_in_function('s, t = "columns", "name"', "print(s, t)"), "s", id="destructuring-target"),
        pytest.param(_in_function('s, *rest = "columns", "name", "x"', "print(s, rest)"), "s", id="starred-target"),
        pytest.param(_in_function('if (s := "columns"):', "    print(s)"), "s", id="walrus"),
        pytest.param(_in_function('s = "columns"', 's += "_x"', "print(s)"), "s", id="augmented-assignment"),
        pytest.param(_in_function("try:", "    pass", "except ValueError as s:", "    print(s)"), "s", id="except"),
        pytest.param(_in_function('with open("columns") as s:', "    print(s)"), "s", id="with"),
        pytest.param("import pkg.a as s\n\nprint(s)\n", "s", id="import-of-a-module"),
        pytest.param('def f() -> None:\n    global NAME\n    NAME = "columns"\n    print(NAME)\n', "NAME", id="global"),
        pytest.param(
            'def outer() -> None:\n    s = "name"\n\n    def inner() -> None:\n        nonlocal s\n        s = "columns"\n'
            "        print(s)\n\n    inner()\n", "s", id="nonlocal"),
        pytest.param('class K:\n    NAME = "columns"\n\n\ndef f(k: K) -> None:\n    print(k.NAME)\n', "k.NAME",
                     id="attribute-of-a-parameter"),
    ],
)
def test_a_name_bound_any_other_way_has_no_sources(tmp_path: Path, use: str, read: str) -> None:
    _check(tmp_path, {**A, USE: use}, read, [])


@pytest.mark.parametrize(
    "use",
    [
        pytest.param(_in_function('for s in frozenset({"columns"}):', "    print(s)"), id="frozenset"),
        pytest.param(_in_function('for s in {"columns": 1}:', "    print(s)"), id="dict-display"),
        pytest.param(_in_function('for s, t in (("columns", "name"),):', "    print(s, t)"), id="destructuring-target"),
        pytest.param(_in_function('for s in ("columns", "name"):', "    print(s)", '    s = "x"'), id="target-bound-again"),
        pytest.param(_in_function('xs = ("columns",)', 'xs = ("name",)', "for s in xs:", "    print(s)"),
                     id="display-name-bound-twice"),
        pytest.param(_in_function('xs = ["columns"]', 'xs.append("name")', "for s in xs:", "    print(s)"),
                     id="display-appended-to"),
        pytest.param(_in_function('xs = ["columns"]', 'xs[0] = "name"', "for s in xs:", "    print(s)"),
                     id="display-item-assigned"),
        pytest.param(_in_function('xs = ["columns"]', "ys = xs", 'ys.append("name")', "for s in xs:", "    print(s)"),
                     id="display-appended-to-through-an-alias"),
        pytest.param(_in_function('xs = ["columns"]', "ys = xs", "zs: list[str] = ys", 'zs[0] = "name"', "for s in xs:",
                                  "    print(s)"), id="display-item-assigned-through-two-aliases"),
        pytest.param(_in_function('xs = ["columns"]', "ys = zs = xs", 'zs.append("name")', "for s in xs:", "    print(s)"),
                     id="display-appended-to-through-a-chained-alias"),
        pytest.param(_in_function('xs = ["columns"]', "ys = xs", 'ys += ["name"]', "for s in xs:", "    print(s)"),
                     id="display-augmented-through-an-alias"),
        pytest.param(_in_function('xs = ["columns"]', 'xs += ["name"]', "for s in xs:", "    print(s)"),
                     id="display-augmented"),
        pytest.param('XS = ["columns"]\n\n\ndef g() -> None:\n    XS.append("name")\n\n\n'
                     + _in_function("for s in XS:", "    print(s)"), id="module-display-appended-to-elsewhere"),
        pytest.param(_in_function('print([str(s) for s in frozenset({"columns"})])'), id="comprehension-over-a-frozenset"),
        pytest.param(_in_function("print([str(s) for s in p])"), id="comprehension-over-a-parameter"),
    ],
)
def test_a_loop_over_anything_but_an_unmutated_display_has_no_sources(tmp_path: Path, use: str) -> None:
    _check(tmp_path, {USE: use}, "s", [])


STUB = 'from typing import Final\n\nDEFAULT: Final = "columns"\n'


@pytest.mark.parametrize(
    "files",
    [
        pytest.param({"../site/dep/__init__.py": "", "../site/dep/consts.py": 'DEFAULT = "columns"\n',
                      USE: "from dep.consts import DEFAULT\n\nprint(DEFAULT)\n"}, id="dependency"),
        pytest.param({"pkg/consts.pyi": STUB, USE: "from pkg.consts import DEFAULT\n\nprint(DEFAULT)\n"}, id="stub"),
        pytest.param({"pkg/consts.pyi": STUB, "pkg/consts.py": "import os\n\nDEFAULT = os.sep\n",
                      USE: "from pkg.consts import DEFAULT\n\nprint(DEFAULT)\n"}, id="stub-beside-its-module"),
    ],
)
def test_a_literal_outside_the_projects_sources_is_no_source(tmp_path: Path, files: dict[str, str]) -> None:
    root = tmp_path.resolve() / "proj"
    for rel, text in files.items():
        if rel.endswith(".py"):
            ast.parse(text)
    assert _found(root, files, "DEFAULT") == []
