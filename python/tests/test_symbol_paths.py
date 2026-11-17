"""Python `dr-refactor --symbol`: a declaration located by its path inside `--file`."""

from __future__ import annotations

from pathlib import Path

import pytest
from project_files import file_tree, write_project
from refactor_cli import assert_same_run, line_col, read, run

from living_architecture.contract import message
from living_architecture.refactor.python_source import SourceFile
from living_architecture.refactor.symbol_path import LocatorError, locate

STORAGE = """\
class StorageBackend:
    def get_model(self, model_name: str) -> int:
        return len(model_name)

    def save_model(self, model_name: str) -> None:
        print(model_name)


class _ProjectionPlan:
    measures: list[str] = []

    def total(self) -> int:
        return len(self.measures)


measures = 3


def build() -> int:
    def inner() -> int:
        return 1

    return inner()


def inner() -> int:
    return 2


def get_model(model_name: str) -> str:
    return model_name
"""
STORAGE_USE = """\
from pkg.storage import StorageBackend, _ProjectionPlan, get_model, inner, measures


def use(s: StorageBackend, p: _ProjectionPlan) -> object:
    return s.get_model(model_name="m"), p.measures, measures, get_model("x"), inner()
"""
FILES = {"pkg/storage.py": STORAGE, "pkg/use.py": STORAGE_USE}


def _rename(rel: str, locator: list[str], new_name: str, *, apply: bool = True) -> list[str]:
    return [*(["--apply"] if apply else []), "rename", "--file", rel, *locator, "--new-name", new_name]


def _by_symbol(rel: str, symbol: str, new_name: str, *, apply: bool = True) -> list[str]:
    return _rename(rel, ["--symbol", symbol], new_name, apply=apply)


def _by_position(tmp_path: Path, files: dict[str, str], rel: str, needle: str, nth: int = 0) -> list[str]:
    return line_col(write_project(tmp_path / "probe", files), rel, needle, nth)


def test_method_by_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    position = _by_position(tmp_path, FILES, "pkg/storage.py", "get_model")
    assert_same_run(tmp_path, FILES, _rename("pkg/storage.py", position, "load_model"),
                    _by_symbol("pkg/storage.py", "StorageBackend.get_model", "load_model"), monkeypatch, capsys)


@pytest.mark.parametrize(
    ("symbol", "needle", "nth", "kept"),
    [
        ("build.<locals>.inner", "inner", 0, "def inner() -> int:\n    return 2"),
        ("StorageBackend.get_model(model_name)", "model_name", 0, "def save_model(self, model_name: str)"),
        ("_ProjectionPlan.measures", "measures", 0, "measures = 3"),
    ],
    ids=["nested-function", "parameter", "field"],
)
def test_nested_function_parameter_and_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    symbol: str,
    needle: str,
    nth: int,
    kept: str,
) -> None:
    position = _by_position(tmp_path, FILES, "pkg/storage.py", needle, nth)
    root = assert_same_run(tmp_path, FILES, _rename("pkg/storage.py", position, "renamed"),
                           _by_symbol("pkg/storage.py", symbol, "renamed"), monkeypatch, capsys)
    assert kept in read(root, "pkg/storage.py")


INSTANCE = """\
class C:
    def __init__(self) -> None:
        self.cache: dict[str, int] = {}

    def get(self, key: str) -> int:
        return self.cache[key]


def peek(c: C) -> int:
    return len(c.cache)
"""


def test_instance_attribute_by_class_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"pkg/c.py": INSTANCE}
    position = _by_position(tmp_path, files, "pkg/c.py", "cache")
    root = assert_same_run(tmp_path, files, _rename("pkg/c.py", position, "store"),
                           _by_symbol("pkg/c.py", "C.cache", "store"), monkeypatch, capsys)
    assert "cache" not in read(root, "pkg/c.py")


ENGINE = "class Engine:\n    def run(self) -> None:\n        pass\n"
IMPORTER = "from pkg.engine import Engine\n\n\ndef make() -> Engine:\n    return Engine()\n"


def test_import_binding_equals_the_declaration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"pkg/engine.py": ENGINE, "pkg/importer.py": IMPORTER}
    position = _by_position(tmp_path, files, "pkg/engine.py", "Engine")
    assert_same_run(tmp_path, files, _rename("pkg/engine.py", position, "Motor"),
                    _by_symbol("pkg/importer.py", "Engine", "Motor"), monkeypatch, capsys)


DECLARATION_KINDS = """\
import json as codec

LIMIT = 3


class Outer:
    kind = "x"
    size: int = 0

    class Inner:
        pass

    @property
    def area(self) -> int:
        return self.size


def use(o: Outer) -> object:
    return codec.dumps(LIMIT), o.kind, o.size, Outer.Inner(), o.area
"""


@pytest.mark.parametrize(
    ("symbol", "needle"),
    [("codec", "codec"), ("LIMIT", "LIMIT"), ("Outer.kind", "kind"), ("Outer.size", "size"),
     ("Outer.Inner", "Inner"), ("Outer.area", "area")],
    ids=["import-alias", "module-assignment", "class-assignment", "annotated-field", "nested-class", "property"],
)
def test_every_declaration_kind_has_a_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], symbol: str, needle: str
) -> None:
    files = {"pkg/kinds.py": DECLARATION_KINDS}
    position = _by_position(tmp_path, files, "pkg/kinds.py", needle)
    assert_same_run(tmp_path, files, _rename("pkg/kinds.py", position, "renamed"),
                    _by_symbol("pkg/kinds.py", symbol, "renamed"), monkeypatch, capsys)


GROUPED = {
    "overloads": (
        (
            "from typing import overload\n\n\n"
            "@overload\ndef parse(x: int) -> int: ...\n@overload\ndef parse(x: str) -> str: ...\n"
            "def parse(x: int | str) -> int | str:\n    return x\n\n\n"
            "def use() -> object:\n    return parse(1), parse('a')\n"
        ),
        "parse", "def parse", 3,
    ),
    "property-setter": (
        (
            "class C:\n    def __init__(self) -> None:\n        self._v = 0\n\n"
            "    @property\n    def value(self) -> int:\n        return self._v\n\n"
            "    @value.setter\n    def value(self, v: int) -> None:\n        self._v = v\n\n\n"
            "def use(c: C) -> int:\n    c.value = 2\n    return c.value\n"
        ),
        "C.value", "def value", 2,
    ),
    "self-attribute-in-several-methods": (
        (
            "class C:\n    def __init__(self) -> None:\n        self.x = 1\n\n"
            "    def reset(self) -> None:\n        self.x = 0\n\n\n"
            "def use(c: C) -> int:\n    return c.x\n"
        ),
        "C.x", "self.x =", 2,
    ),
    "conditional-definitions": (
        (
            "import sys\n\nif sys.platform == 'win32':\n    def home() -> str:\n        return 'C:'\n"
            "else:\n    def home() -> str:\n        return '/'\n\n\ndef use() -> str:\n    return home()\n"
        ),
        "home", "def home", 2,
    ),
    "redefinition": (
        (
            "def step() -> int:\n    return 1\n\n\ndef step() -> int:\n    return 2\n\n\n"
            "def use() -> int:\n    return step()\n"
        ),
        "step", "def step", 2,
    ),
}


@pytest.mark.parametrize("construct", list(GROUPED))
def test_declarations_of_one_checker_symbol_are_one_symbol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], construct: str
) -> None:
    source, symbol, declaration, count = GROUPED[construct]
    root = write_project(tmp_path / "proj", {"pkg/m.py": source})
    code, _out, err = run(root, _by_symbol("pkg/m.py", symbol, "renamed"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    renamed = declaration.replace(symbol.split(".")[-1], "renamed")
    assert read(root, "pkg/m.py").count(renamed) == count


def test_unresolved_path_lists_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", FILES)
    before = file_tree(root)
    result = run(root, _by_symbol("pkg/storage.py", "StorageBackend.get_modle", "x"), monkeypatch, capsys)
    expected = message("refactor.symbol-unresolved", path="pkg/storage.py", symbol="StorageBackend.get_modle",
                       candidates="get_model, save_model")
    assert result == (2, "", f"{expected}\n")
    assert file_tree(root) == before


TWICE = "class C:\n    def run(self) -> None:\n        pass\n\n\nclass C:\n    def run(self) -> None:\n        pass\n"


def test_ambiguous_path_lists_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/a.py": TWICE})
    before = file_tree(root)
    result = run(root, _by_symbol("pkg/a.py", "C.run", "go"), monkeypatch, capsys)
    expected = message("refactor.symbol-ambiguous", path="pkg/a.py", symbol="C.run",
                       candidates="pkg/a.py:2, pkg/a.py:7")
    assert result == (2, "", f"{expected}\n")
    assert file_tree(root) == before


def test_two_locators_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_project(tmp_path / "proj", FILES)
    before = file_tree(root)
    code, out, _err = run(root, _rename("pkg/storage.py", ["--symbol", "inner", "--line", "3"], "x"), monkeypatch,
                          capsys)
    assert (code, out) == (2, "")
    assert file_tree(root) == before


def test_out_of_range_line_keeps_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", FILES)
    expected = message("refactor.line-out-of-range", line=999, count=len(STORAGE.splitlines()))
    assert run(root, _rename("pkg/storage.py", ["--line", "999"], "x"), monkeypatch, capsys) == (1, "", f"{expected}\n")


ASYNC = """\
class A:
    async def get_model(self, x: int) -> None: ...


class B(A):
    async def get_model(self, x: int) -> None: ...


async def run() -> None:
    a = A()
    await a.get_model(1)
"""


def test_async_method_by_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    files = {"pkg/a.py": ASYNC}
    position = _by_position(tmp_path, files, "pkg/a.py", "get_model")
    root = assert_same_run(tmp_path, files, _rename("pkg/a.py", position, "load"),
                           _by_symbol("pkg/a.py", "A.get_model", "load"), monkeypatch, capsys)
    assert read(root, "pkg/a.py").count("load") == 3


KWONLY = {
    "pkg/kw.py": "def kwonly(*, model_name: str) -> str:\n    return model_name\n",
    "pkg/call.py": 'from pkg.kw import kwonly\n\n\ndef c() -> str:\n    return kwonly(model_name="x")\n',
}


def test_parameter_by_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    position = _by_position(tmp_path, KWONLY, "pkg/kw.py", "model_name")
    root = assert_same_run(tmp_path, KWONLY, _rename("pkg/kw.py", position, "dataset_name"),
                           _by_symbol("pkg/kw.py", "kwonly(model_name)", "dataset_name"), monkeypatch, capsys)
    assert 'kwonly(dataset_name="x")' in read(root, "pkg/call.py")


def test_dry_run_by_path_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", FILES)
    before = file_tree(root)
    code, out, _err = run(root, _by_symbol("pkg/storage.py", "get_model", "load", apply=False), monkeypatch, capsys)
    assert code == 0
    assert message("refactor.dry-run", count=2) in out
    assert file_tree(root) == before
    assert not (root / ".ropeproject").exists()


def test_move_symbol_by_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    files = {**FILES, "pkg/dest.py": "X = 1\n"}
    position = _by_position(tmp_path, files, "pkg/storage.py", "def get_model(model_name")
    position[-1] = str(int(position[-1]) + len("def "))
    assert_same_run(
        tmp_path, files,
        ["--apply", "move-symbol", "--file", "pkg/storage.py", *position, "--dest", "pkg/dest.py"],
        ["--apply", "move-symbol", "--file", "pkg/storage.py", "--symbol", "get_model", "--dest", "pkg/dest.py"],
        monkeypatch, capsys,
    )


def test_move_symbol_takes_only_a_top_level_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {**FILES, "pkg/dest.py": "X = 1\n"})
    before = file_tree(root)
    argv = ["--apply", "move-symbol", "--file", "pkg/storage.py", "--symbol", "StorageBackend.get_model",
            "--dest", "pkg/dest.py"]
    code, out, err = run(root, argv, monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert err == f"{message('refactor.not-movable', path='pkg/storage.py')}\n"
    assert file_tree(root) == before


def _locate(text: str, path: str) -> int:
    return locate(SourceFile(Path("m.py"), text), path, "m.py").offset


RECEIVERS = """\
class A:
    @staticmethod
    def update(other: "A") -> None:
        other.value = 1


class C:
    def method(self) -> None:
        class Inner:
            def __init__(self) -> None:
                self.value = 1

        self.other = Inner()

    def bump(self) -> None:
        self.count += 1
"""


@pytest.mark.parametrize("path", ["A.value", "C.value"])
def test_a_static_method_parameter_or_a_nested_method_receiver_declares_no_member(path: str) -> None:
    with pytest.raises(LocatorError):
        _locate(RECEIVERS, path)


def test_receiver_stores_declare_members() -> None:
    assert (_locate(RECEIVERS, "C.other"), _locate(RECEIVERS, "C.count")) == (
        RECEIVERS.index("other ="), RECEIVERS.index("count +="))


@pytest.mark.parametrize("name", ["a", "b", "c", "d", "e"], ids=["positional-only", "plain", "star", "keyword-only", "double-star"])
def test_a_parameter_of_every_kind_is_located_by_path(name: str) -> None:
    text = "def f(a, /, b, *c, d, **e) -> None:\n    pass\n"
    assert _locate(text, f"f({name})") == text.index(name, text.index("("))


def test_loop_and_with_targets_are_locals() -> None:
    text = "def f() -> None:\n    for item in [1]:\n        print(item)\n    with open('x') as handle:\n        print(handle)\n"
    assert (_locate(text, "f.<locals>.item"), _locate(text, "f.<locals>.handle")) == (text.index("item"), text.index("handle"))


def test_a_file_with_a_coding_cookie_is_located_in_its_encoding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    text = '# -*- coding: latin-1 -*-\nNAME = "café"\n\n\ndef old() -> str:\n    return NAME\n'
    root = write_project(tmp_path / "proj", {"pkg/__init__.py": ""})
    (root / "pkg/l1.py").write_bytes(text.encode("latin-1"))
    code, _out, err = run(root, _by_symbol("pkg/l1.py", "old", "new"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert (root / "pkg/l1.py").read_bytes() == text.replace("def old", "def new").encode("latin-1")


def test_out_of_range_column_and_offset_keep_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", FILES)
    width = len(STORAGE.splitlines()[0])
    column = message("refactor.col-out-of-range", col=width + 2, line=1, count=width)
    offset = message("refactor.offset-out-of-range", offset=len(STORAGE) + 1, count=len(STORAGE))
    assert run(root, _rename("pkg/storage.py", ["--line", "1", "--col", str(width + 2)], "x"), monkeypatch, capsys) == (
        1, "", f"{column}\n")
    assert run(root, _rename("pkg/storage.py", ["--offset", str(len(STORAGE) + 1)], "x"), monkeypatch, capsys) == (
        1, "", f"{offset}\n")
