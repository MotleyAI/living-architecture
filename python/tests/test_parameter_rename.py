"""Python `dr-refactor rename` of a parameter: every kind, its hierarchy, its overload group and name conflicts."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from string import Template

import pytest
from project_files import file_tree

from living_architecture.cli import dr_refactor
from living_architecture.contract import message

MakeProject = Callable[..., Path]
OLD = "model_name"
NEW = "dataset_name"


def _rename(root: Path, rel: str, offset: int, *flags: str, new_name: str = NEW) -> int:
    return dr_refactor(["--project", str(root), "--apply", "rename", "--file", str(root / rel), "--offset", str(offset),
                        "--new-name", new_name, *flags])


def _at(root: Path, rel: str, needle: str, nth: int = 0) -> int:
    """The offset of `needle`'s `nth` occurrence in `rel`."""
    text = _read(root, rel)
    offset = -1
    for _ in range(nth + 1):
        offset = text.index(needle, offset + 1)
    return offset


def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def _expect(root: Path, expected: dict[str, str]) -> None:
    assert {rel: _read(root, rel) for rel in expected} == expected


# --- every kind ---------------------------------------------------------------------------------------------------

MIXED = Template(
    "def f(a: int, /, $b: int, *xs: int, $c: int = 0, **kw: int) -> int:\n"
    "    return a + $b + sum(xs) + $c + sum(kw.values())\n\n\n"
    "def g($a: int, /, *$args: int, **$kwargs: int) -> None:\n"
    "    print($a, $args, $kwargs)\n"
)
MIXED_USE = Template(
    "from pkg.mixed import f, g\n\n\n"
    "def calls() -> None:\n"
    "    f(1, 2, 3, $c=4, d=5)\n"
    "    f(1, $b=2)\n"
    "    f(1, 2, a=3)\n"
    "    g(1, a=2, args=3, kwargs=4)\n"
)
MIXED_NAMES = {"a": "a", "b": "b", "c": "c", "args": "args", "kwargs": "kwargs"}


@pytest.mark.parametrize(
    ("needle", "param", "new_name"),
    [
        ("b: int", "b", "bb"),
        ("c: int", "c", "cc"),
        ("a: int, /, *", "a", "aa"),
        ("args: int", "args", "rest"),
        ("kwargs: int", "kwargs", "options"),
    ],
    ids=["positional-or-keyword", "keyword-only", "positional-only", "args", "kwargs"],
)
def test_each_rename_changes_only_the_keywords_that_bind_it(
    typed_project: MakeProject, needle: str, param: str, new_name: str
) -> None:
    root = typed_project({"pkg/mixed.py": MIXED.substitute(MIXED_NAMES), "pkg/use.py": MIXED_USE.substitute(MIXED_NAMES)})
    assert _rename(root, "pkg/mixed.py", _at(root, "pkg/mixed.py", needle), new_name=new_name) == 0
    names = {**MIXED_NAMES, param: new_name}
    _expect(root, {"pkg/mixed.py": MIXED.substitute(names), "pkg/use.py": MIXED_USE.substitute(names)})


KW = (
    "def kwonly(*, model_name: str) -> str:\n    return model_name\n\n\n"
    "def star(*xs: int, model_name: str) -> str:\n    return model_name + str(len(xs))\n\n\n"
    "def posonly(model_name: str, /) -> str:\n    return model_name\n"
)
KW_USE = (
    "import functools\n\n"
    "from pkg.kw import kwonly, posonly, star\n\n\n"
    "def wrap(**kw: str) -> str:\n    return kwonly(**kw)\n\n\n"
    "def calls() -> list[object]:\n"
    "    return [\n"
    '        kwonly(model_name="x"),\n'
    '        star(1, 2, model_name="x"),\n'
    '        posonly("x"),\n'
    '        kwonly(**{"model_name": "x"}),\n'
    '        wrap(model_name="x"),\n'
    '        functools.partial(kwonly, model_name="x"),\n'
    "    ]\n"
)
KWONLY_RENAMED = KW.replace("kwonly(*, model_name: str) -> str:\n    return model_name",
                            "kwonly(*, dataset_name: str) -> str:\n    return dataset_name")


@pytest.mark.parametrize(
    ("rel", "needle"),
    [("pkg/kw.py", "model_name"), ("pkg/kw.py", "return model_name"), ("pkg/use.py", 'kwonly(model_name="x")')],
    ids=["declaration", "body-use", "call-keyword"],
)
def test_keyword_only_parameter_located_anywhere(typed_project: MakeProject, rel: str, needle: str) -> None:
    root = typed_project({"pkg/kw.py": KW, "pkg/use.py": KW_USE})
    offset = _at(root, rel, needle) + needle.index(OLD)
    assert _rename(root, rel, offset) == 0
    _expect(root, {
        "pkg/kw.py": KWONLY_RENAMED,
        "pkg/use.py": KW_USE.replace('kwonly(model_name="x")', 'kwonly(dataset_name="x")')
                            .replace('kwonly, model_name="x"', 'kwonly, dataset_name="x"'),
    })


NESTED = Template(
    "def outer(*, $p: str) -> list[str]:\n"
    "    def inner() -> str:\n        return $p.upper()\n\n"
    "    return [inner(), *($p for _ in range(2)), (lambda: $p)()]\n\n\n"
    'x = outer($p="y")\n'
)


def test_uses_in_nested_scopes_are_renamed(typed_project: MakeProject) -> None:
    root = typed_project({"pkg/n.py": NESTED.substitute(p=OLD)})
    assert _rename(root, "pkg/n.py", _at(root, "pkg/n.py", OLD)) == 0
    _expect(root, {"pkg/n.py": NESTED.substitute(p=NEW)})


def test_keyword_only_parameter_after_args(typed_project: MakeProject) -> None:
    root = typed_project({"pkg/kw.py": KW, "pkg/use.py": KW_USE})
    assert _rename(root, "pkg/kw.py", _at(root, "pkg/kw.py", OLD, nth=2)) == 0
    _expect(root, {
        "pkg/kw.py": KW.replace("model_name: str) -> str:\n    return model_name + str",
                                "dataset_name: str) -> str:\n    return dataset_name + str"),
        "pkg/use.py": KW_USE.replace('star(1, 2, model_name="x")', 'star(1, 2, dataset_name="x")'),
    })


def test_positional_only_parameter_leaves_calls_unchanged(typed_project: MakeProject) -> None:
    root = typed_project({"pkg/kw.py": KW, "pkg/use.py": KW_USE})
    assert _rename(root, "pkg/kw.py", _at(root, "pkg/kw.py", OLD, nth=4)) == 0
    _expect(root, {
        "pkg/kw.py": KW.replace("posonly(model_name: str, /) -> str:\n    return model_name",
                                "posonly(dataset_name: str, /) -> str:\n    return dataset_name"),
        "pkg/use.py": KW_USE,
    })


# --- hierarchy ----------------------------------------------------------------------------------------------------

BASE = Template(
    "class A:\n    def run(self, *, $a: str) -> str:\n        return $a\n\n\n"
    'def base_calls(a: A) -> str:\n    return a.run($ca="x")\n'
)
SUB = Template(
    "from pkg.base import A\n\n\n"
    "class B(A):\n    def run(self, *, $b: str) -> str:\n        return super().run($sup=$b)\n\n\n"
    "class Other(A):\n    def run(self, *, name: str) -> str:\n        return name\n\n\n"
    'class Bare(A):\n    def run(self) -> str:  # pyright: ignore[reportIncompatibleMethodOverride]\n        return ""\n\n\n'
    'def sub_calls(b: B, o: Other) -> str:\n    return b.run($cb="y") + o.run(name="z")\n'
)
ALL_OLD = {"a": OLD, "ca": OLD, "b": OLD, "sup": OLD, "cb": OLD}


def _hierarchy(**renamed: str) -> dict[str, str]:
    names = {**ALL_OLD, **renamed}
    return {"pkg/base.py": BASE.substitute(names), "pkg/sub.py": SUB.substitute(names)}


EVERY = dict.fromkeys(ALL_OLD, NEW)


@pytest.mark.parametrize(
    ("rel", "flags", "expected"),
    [
        ("pkg/base.py", (), EVERY),
        ("pkg/sub.py", (), EVERY),
        ("pkg/base.py", ("--no-in-hierarchy",), {"a": NEW, "ca": NEW, "sup": NEW}),
        ("pkg/sub.py", ("--no-in-hierarchy",), {"b": NEW, "cb": NEW}),
    ],
    ids=["at-base", "at-override", "at-base-hierarchy-off", "at-override-hierarchy-off"],
)
def test_keyword_only_parameter_across_overrides(
    typed_project: MakeProject, rel: str, flags: tuple[str, ...], expected: dict[str, str]
) -> None:
    root = typed_project(_hierarchy())
    assert _rename(root, rel, _at(root, rel, f"{OLD}: str"), *flags) == 0
    _expect(root, _hierarchy(**expected))


POSITIONAL = Template(
    "class A:\n    def run(self, $a: str) -> str:\n        return $a\n\n\n"
    "class B(A):\n    def run(self, $b: str) -> str:\n        return $b.upper()\n\n\n"
    'def calls(a: A, b: B) -> str:\n    return a.run($ca="x") + b.run($cb="y") + a.run("z")\n'
)


def test_positional_or_keyword_parameter_across_an_override(typed_project: MakeProject) -> None:
    root = typed_project({"pkg/a.py": POSITIONAL.substitute(a=OLD, b=OLD, ca=OLD, cb=OLD)})
    assert _rename(root, "pkg/a.py", _at(root, "pkg/a.py", OLD)) == 0
    _expect(root, {"pkg/a.py": POSITIONAL.substitute(a=NEW, b=NEW, ca=NEW, cb=NEW)})


KINDS = Template(
    "class A:\n"
    "    @classmethod\n    def cm(cls, *, $cm: str) -> str:\n        return $cm\n\n"
    "    @staticmethod\n    def sm(*, $sm: str) -> str:\n        return $sm\n\n"
    "    async def am(self, *, $am: str) -> str:\n        return $am\n\n\n"
    "class B(A):\n"
    "    @classmethod\n    def cm(cls, *, $cm: str) -> str:\n        return $cm.upper()\n\n"
    "    @staticmethod\n    def sm(*, $sm: str) -> str:\n        return $sm.upper()\n\n"
    "    async def am(self, *, $am: str) -> str:\n        return $am.upper()\n\n\n"
    'async def calls(b: B) -> str:\n    return A.cm($cm="x") + A.sm($sm="y") + await b.am($am="z")\n'
)


@pytest.mark.parametrize("method", ["cm", "sm", "am"], ids=["classmethod", "staticmethod", "async"])
@pytest.mark.parametrize("located", ["A", "B"])
def test_class_static_and_async_methods_follow_the_hierarchy(
    typed_project: MakeProject, method: str, located: str
) -> None:
    names = {"cm": OLD, "sm": OLD, "am": OLD}
    root = typed_project({"pkg/k.py": KINDS.substitute(names)})
    nth = {"cm": 0, "sm": 2, "am": 4}[method] + (0 if located == "A" else 6)
    assert _rename(root, "pkg/k.py", _at(root, "pkg/k.py", OLD, nth=nth)) == 0
    _expect(root, {"pkg/k.py": KINDS.substitute({**names, method: NEW})})


# --- overload groups ----------------------------------------------------------------------------------------------

OVERLOADS = Template(
    "$header\n\n\n"
    "@$deco\ndef f(*, $s1: str) -> str: ...\n"
    "@$deco\ndef f(*, $s2: int) -> int: ...\n"
    "def f(*, $impl: str | int) -> str | int:\n    return $impl\n"
)
OVERLOAD_USE = Template('from pkg.ovl import f\n\nx = f($kw="x")\n')
SPELLINGS = [
    pytest.param("from typing import overload", "overload", id="typing"),
    pytest.param("import typing", "typing.overload", id="typing-module"),
    pytest.param("from typing_extensions import overload", "overload", id="typing-extensions"),
    pytest.param("from typing import overload as ov", "ov", id="aliased"),
]


def _overloads(header: str, deco: str, name: str) -> dict[str, str]:
    return {
        "pkg/ovl.py": OVERLOADS.substitute(header=header, deco=deco, s1=name, s2=name, impl=name),
        "pkg/use.py": OVERLOAD_USE.substitute(kw=name),
    }


@pytest.mark.parametrize(("header", "deco"), SPELLINGS)
@pytest.mark.parametrize("member", [0, 1, 2], ids=["first-stub", "second-stub", "implementation"])
@pytest.mark.parametrize("flags", [(), ("--no-in-hierarchy",)], ids=["hierarchy", "no-hierarchy"])
def test_overload_group_follows_from_any_member(
    typed_project: MakeProject, header: str, deco: str, member: int, flags: tuple[str, ...]
) -> None:
    root = typed_project(_overloads(header, deco, OLD))
    assert _rename(root, "pkg/ovl.py", _at(root, "pkg/ovl.py", OLD, nth=member), *flags) == 0
    _expect(root, _overloads(header, deco, NEW))


NOT_OVERLOADS = Template(
    "${header}def f(*, $first: str) -> str:\n    return $first\n\n\n"
    "${deco}def f(*, model_name: int) -> int:  # pyright: ignore[reportRedeclaration]\n    return model_name\n\n\n"
    "x = f(model_name=1)\n"
)


@pytest.mark.parametrize(
    ("header", "deco"),
    [
        ("", ""),
        ("def overload(fn: object) -> object:\n    return fn\n\n\n", "@overload  # pyright: ignore[reportUntypedFunctionDecorator]\n"),
    ],
    ids=["plain-redefinition", "local-decorator-named-overload"],
)
def test_same_named_defs_without_a_resolved_overload_are_no_group(
    typed_project: MakeProject, header: str, deco: str
) -> None:
    source = NOT_OVERLOADS.substitute(header=header, deco=deco, first=OLD)
    root = typed_project({"pkg/m.py": source})
    assert _rename(root, "pkg/m.py", _at(root, "pkg/m.py", OLD)) == 0
    _expect(root, {"pkg/m.py": NOT_OVERLOADS.substitute(header=header, deco=deco, first=NEW)})


PROTOCOL = Template(
    "from typing import Protocol, overload\n\n\n"
    "class P(Protocol):\n"
    "    @overload\n    def get(self, *, $s1: str) -> str: ...\n"
    "    @overload\n    def get(self, *, $s2: int) -> int: ...\n\n\n"
    'def use(p: P) -> str:\n    return p.get($kw="x")\n'
)


@pytest.mark.parametrize("member", [0, 1], ids=["first-stub", "second-stub"])
def test_overload_group_without_an_implementation(typed_project: MakeProject, member: int) -> None:
    root = typed_project({"pkg/p.py": PROTOCOL.substitute(s1=OLD, s2=OLD, kw=OLD)})
    assert _rename(root, "pkg/p.py", _at(root, "pkg/p.py", OLD, nth=member)) == 0
    _expect(root, {"pkg/p.py": PROTOCOL.substitute(s1=NEW, s2=NEW, kw=NEW)})


OVERLOADED_METHOD = Template(
    "from typing import overload\n\n\n"
    "class A:\n"
    "    @overload\n    def run(self, *, $s1: str) -> str: ...\n"
    "    @overload\n    def run(self, *, $s2: int) -> int: ...\n"
    "    def run(self, *, $impl: str | int) -> str | int:\n        return $impl\n\n\n"
    "class B(A):\n"
    "    def run(self, *, $b: str | int) -> str | int:  # pyright: ignore[reportIncompatibleMethodOverride]\n"
    "        return $b\n\n\n"
    'def calls(a: A, b: B) -> object:\n    return a.run($ca="x"), b.run($cb=1)\n'
)
METHOD_OLD = {"s1": OLD, "s2": OLD, "impl": OLD, "b": OLD, "ca": OLD, "cb": OLD}
A_GROUP = {"s1": NEW, "s2": NEW, "impl": NEW, "ca": NEW}


@pytest.mark.parametrize(
    ("member", "flags", "renamed"),
    [
        (2, (), dict.fromkeys(METHOD_OLD, NEW)),
        (0, (), dict.fromkeys(METHOD_OLD, NEW)),
        (2, ("--no-in-hierarchy",), A_GROUP),
        (1, ("--no-in-hierarchy",), A_GROUP),
    ],
    ids=["implementation", "stub", "implementation-hierarchy-off", "stub-hierarchy-off"],
)
def test_overloaded_method_in_a_hierarchy(
    typed_project: MakeProject, member: int, flags: tuple[str, ...], renamed: dict[str, str]
) -> None:
    root = typed_project({"pkg/a.py": OVERLOADED_METHOD.substitute(METHOD_OLD)})
    assert _rename(root, "pkg/a.py", _at(root, "pkg/a.py", OLD, nth=member), *flags) == 0
    _expect(root, {"pkg/a.py": OVERLOADED_METHOD.substitute({**METHOD_OLD, **renamed})})


# --- name conflicts -----------------------------------------------------------------------------------------------

def _refused(
    root: Path, rel: str, offset: int, capsys: pytest.CaptureFixture[str], path: str, line: int
) -> None:
    before = file_tree(root)
    assert _rename(root, rel, offset) == 1
    assert capsys.readouterr() == ("", message("refactor.name-conflict", name=NEW, path=path, line=line) + "\n")
    assert file_tree(root) == before


CONFLICTS = Template(
    'dataset_name = "d"\n\n\n'                                            # 1
    "def g(${star}model_name: str, dataset_name: str) -> str:\n"         # 4
    "    return model_name + dataset_name\n\n\n"
    "def h(${star}model_name: str) -> str:\n"
    "    return dataset_name + model_name\n\n\n"                         # 9
    "def k(${star}model_name: str) -> str:\n"
    "    dataset_name = model_name.upper()\n"                            # 13
    "    return dataset_name\n\n\n"
    "def n(${star}model_name: str) -> str:\n"
    "    def inner() -> str:\n"
    "        return dataset_name\n"                                      # 19
    "    return inner() + model_name\n"
)


@pytest.mark.parametrize("star", ["*, ", ""], ids=["keyword-only", "positional-or-keyword"])
@pytest.mark.parametrize(
    ("function", "line"),
    [("g", 4), ("h", 9), ("k", 13), ("n", 19)],
    ids=["duplicate-parameter", "global-read", "local-assignment", "nested-scope"],
)
def test_new_name_the_function_already_uses_is_refused(
    typed_project: MakeProject, capsys: pytest.CaptureFixture[str], function: str, line: int, star: str
) -> None:
    root = typed_project({"pkg/c.py": CONFLICTS.substitute(star=star)})
    offset = _at(root, "pkg/c.py", f"def {function}({star}model_name") + len(f"def {function}({star}")
    _refused(root, "pkg/c.py", offset, capsys, "pkg/c.py", line)


CLEAN_BASE = "class A:\n    def run(self, *, model_name: str) -> str:\n        return model_name\n"
READING_BASE = (
    'dataset_name = "d"\n\n\n'
    "class A:\n    def run(self, *, model_name: str) -> str:\n        return model_name + dataset_name\n"
)
READING_OVERRIDE = (
    "from pkg.base import A\n\n"
    'dataset_name = "d"\n\n\n'
    "class B(A):\n"
    "    def run(self, *, model_name: str) -> str:\n"
    "        prefix = dataset_name\n"                                    # 8
    "        return prefix + model_name + dataset_name\n"
)


def test_conflict_in_an_override_is_refused(typed_project: MakeProject, capsys: pytest.CaptureFixture[str]) -> None:
    root = typed_project({"pkg/base.py": CLEAN_BASE, "pkg/sub.py": READING_OVERRIDE})
    _refused(root, "pkg/base.py", _at(root, "pkg/base.py", OLD), capsys, "pkg/sub.py", 8)


def test_first_conflict_by_path_then_offset(typed_project: MakeProject, capsys: pytest.CaptureFixture[str]) -> None:
    override = READING_OVERRIDE.replace("pkg.base", "pkg.z_base")
    root = typed_project({"pkg/z_base.py": READING_BASE, "pkg/a_sub.py": override})
    _refused(root, "pkg/z_base.py", _at(root, "pkg/z_base.py", OLD), capsys, "pkg/a_sub.py", 8)


ATTRIBUTES = Template(
    "class O:\n    dataset_name: str = \"\"\n\n\n"
    "def other(*, dataset_name: int) -> None:\n    print(dataset_name)\n\n\n"
    "def m(*, $p: str, o: O) -> str:\n"
    "    other(dataset_name=1)\n"
    "    return o.dataset_name + $p\n"
)


def test_attributes_and_other_calls_keywords_are_no_conflict(typed_project: MakeProject) -> None:
    root = typed_project({"pkg/m.py": ATTRIBUTES.substitute(p=OLD)})
    assert _rename(root, "pkg/m.py", _at(root, "pkg/m.py", OLD)) == 0
    _expect(root, {"pkg/m.py": ATTRIBUTES.substitute(p=NEW)})


@pytest.mark.parametrize(
    ("files", "rel"),
    [
        (_hierarchy(), "pkg/base.py"),
        (_overloads("from typing import overload", "overload", OLD), "pkg/ovl.py"),
        ({"pkg/kw.py": KW, "pkg/use.py": KW_USE}, "pkg/kw.py"),
    ],
    ids=["hierarchy", "overload-group", "function"],
)
def test_rename_to_the_old_name_changes_nothing(typed_project: MakeProject, files: dict[str, str], rel: str) -> None:
    root = typed_project(files)
    before = file_tree(root)
    assert _rename(root, rel, _at(root, rel, OLD), new_name=OLD) == 0
    assert file_tree(root) == before
