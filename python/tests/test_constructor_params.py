"""Python parameter renames on `__init__` and `__new__`: the located constructor and its overload group only."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from project_files import file_tree, write_project
from refactor_cli import read, run

from living_architecture.contract import message

ERRORS = """\
class Base(Exception):
    def __init__(self, msg: str) -> None:
        super().__init__(msg)


class A(Base):
    def __init__(self, msg: str, *, field: str) -> None:
        self.field = field
        super().__init__(msg)


class B(Base):
    def __init__(self, msg: str, *, field: str) -> None:
        self.field = field
        super().__init__(f"field of {field}")


class C(A):
    def __init__(self, msg: str, *, field: str) -> None:
        super().__init__(msg, field=field)

    @classmethod
    def make(cls) -> "C":
        return cls("m", field="c")


def use() -> list[Exception]:
    return [A("x", field="a"), B("y", field="b"), C("z", field="c")]
"""
A_RENAMED = (ERRORS.replace("*, field: str) -> None:\n        self.field = field\n        super().__init__(msg)",
                            "*, column: str) -> None:\n        self.field = column\n        super().__init__(msg)")
             .replace("super().__init__(msg, field=field)", "super().__init__(msg, column=field)")
             .replace('A("x", field="a")', 'A("x", column="a")'))


def _rename(symbol: str, *flags: str) -> list[str]:
    return ["--apply", "rename", "--file", "pkg/e.py", "--symbol", symbol, "--new-name", "column", *flags]


@pytest.mark.parametrize("flags", [(), ("--no-in-hierarchy",)], ids=["default", "no-in-hierarchy"])
def test_an_init_parameter_rename_stays_in_its_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], flags: tuple[str, ...]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/e.py": ERRORS})
    code, _out, err = run(root, _rename("A.__init__(field)", *flags), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/e.py") == A_RENAMED


def test_a_subclass_constructor_rename_leaves_its_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/e.py": ERRORS})
    code, _out, err = run(root, _rename("C.__init__(field)"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/e.py") == (
        ERRORS.replace("*, field: str) -> None:\n        super().__init__(msg, field=field)",
                       "*, column: str) -> None:\n        super().__init__(msg, field=column)")
        .replace('cls("m", field="c")', 'cls("m", column="c")').replace('C("z", field="c")', 'C("z", column="c")'))


def test_a_map_renames_several_constructors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    entries = [{"file": "pkg/e.py", "symbol": f"{cls}.__init__(field)", "new_name": "column"} for cls in ("A", "B")]
    root = write_project(tmp_path / "p", {"pkg/e.py": ERRORS, "map.yaml": yaml.safe_dump(entries)})
    code, _out, err = run(root, ["--apply", "rename-map", "map.yaml"], monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/e.py") == A_RENAMED.replace(
        '*, field: str) -> None:\n        self.field = field\n        super().__init__(f"field of {field}")',
        '*, column: str) -> None:\n        self.field = column\n        super().__init__(f"field of {column}")',
    ).replace('B("y", field="b")', 'B("y", column="b")')


SHAPES = """\
from typing import overload


class N1:
    def __new__(cls, *, field: str) -> "N1":
        print(field)
        return super().__new__(cls)


class N2:
    def __new__(cls, *, field: str) -> "N2":
        print(field)
        return super().__new__(cls)


class Ov:
    @overload
    def __init__(self, *, field: str) -> None: ...
    @overload
    def __init__(self, *, field: int) -> None: ...
    def __init__(self, *, field: str | int) -> None:
        self.value = field


class Ov2(Ov):
    def __init__(self, *, field: str) -> None:
        super().__init__(field=field)


def use() -> list[object]:
    return [N1(field="a"), N2(field="b"), Ov(field="a"), Ov(field=1), Ov2(field="b")]
"""


def test_a_new_parameter_rename_stays_in_its_class_and_renames_its_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/e.py": SHAPES})
    code, _out, err = run(root, _rename("N1.__new__(field)"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/e.py") == (
        SHAPES.replace('*, field: str) -> "N1":\n        print(field)', '*, column: str) -> "N1":\n        print(column)')
        .replace('N1(field="a")', 'N1(column="a")'))


def test_an_overloaded_init_renames_its_whole_group_and_no_subclass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/e.py": SHAPES})
    code, _out, err = run(root, _rename("Ov.__init__(field)"), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/e.py") == (
        SHAPES.replace("*, field: str) -> None: ...", "*, column: str) -> None: ...")
        .replace("*, field: int) -> None: ...", "*, column: int) -> None: ...")
        .replace("*, field: str | int) -> None:\n        self.value = field",
                 "*, column: str | int) -> None:\n        self.value = column")
        .replace("super().__init__(field=field)", "super().__init__(column=field)")
        .replace('Ov(field="a"), Ov(field=1)', 'Ov(column="a"), Ov(column=1)'))


BOTH = """\
class K:
    def __new__(cls, *, field: str) -> "K":
        return super().__new__(cls)

    def __init__(self, *, field: str) -> None:
        self.value = field


def use() -> K:
    return K(field="a")
"""


BOTH_RENAMED = BOTH.replace("field", "column")


@pytest.mark.parametrize("constructor", ["__init__", "__new__"])
def test_one_constructor_of_a_class_declaring_both_lists_the_class_call_keyword(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], constructor: str
) -> None:
    root = write_project(tmp_path / "p", {"pkg/e.py": BOTH})
    before = file_tree(root)
    code, out, err = run(root, _rename(f"K.{constructor}(field)"), monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert err.splitlines() == [
        message("refactor.unlinked-keyword", path="pkg/e.py", line=10, callee="K", old="field"),
        message("refactor.blindspots", count=1, names="field="),
    ]
    assert file_tree(root) == before


DIRECT = BOTH + """

class Sub(K):
    def __init__(self, *, field: str) -> None:
        super().__init__(field=field)


def direct(k: K) -> None:
    K.__init__(k, field="b")
"""


def test_a_constructor_called_by_itself_takes_its_own_keyword(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "p", {"pkg/e.py": DIRECT})
    code, _out, err = run(root, _rename("K.__init__(field)", "--allow-blindspots"), monkeypatch, capsys)
    assert (code, err.splitlines()) == (
        0, [message("refactor.unlinked-keyword", path="pkg/e.py", line=10, callee="K", old="field")])
    assert read(root, "pkg/e.py") == (
        DIRECT.replace("*, field: str) -> None:\n        self.value = field",
                       "*, column: str) -> None:\n        self.value = column")
        .replace("super().__init__(field=field)", "super().__init__(column=field)")
        .replace('K.__init__(k, field="b")', 'K.__init__(k, column="b")'))


INHERITED = """\
class Base:
    def __new__(cls, *, field: str) -> "Base":
        return super().__new__(cls)


class Child(Base):
    def __init__(self, *, field: str) -> None:
        self.value = field


class Grand(Child):
    pass


class Lone:
    def __init__(self, *, field: str) -> None:
        self.value = field


def use() -> list[object]:
    return [Child(field="a"), Grand(field="b"), Lone(field="c")]
"""


@pytest.mark.parametrize("symbol", ["Child.__init__(field)", "Base.__new__(field)"])
def test_an_inherited_constructor_taking_the_keyword_lists_the_class_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], symbol: str
) -> None:
    root = write_project(tmp_path / "p", {"pkg/e.py": INHERITED})
    before = file_tree(root)
    code, out, err = run(root, _rename(symbol), monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert err.splitlines() == [
        message("refactor.unlinked-keyword", path="pkg/e.py", line=21, callee="Child", old="field"),
        message("refactor.unlinked-keyword", path="pkg/e.py", line=21, callee="Grand", old="field"),
        message("refactor.blindspots", count=2, names="field="),
    ]
    assert file_tree(root) == before


def test_a_map_renaming_an_inherited_pair_alike_renames_every_class_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    entries = [{"file": "pkg/e.py", "symbol": symbol, "new_name": "column"}
               for symbol in ("Child.__init__(field)", "Base.__new__(field)", "Lone.__init__(field)")]
    root = write_project(tmp_path / "p", {"pkg/e.py": INHERITED, "map.yaml": yaml.safe_dump(entries)})
    code, _out, err = run(root, ["--apply", "rename-map", "map.yaml"], monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/e.py") == INHERITED.replace("field", "column")


def test_a_map_renaming_both_constructors_alike_renames_the_class_call_keyword(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    entries = [{"file": "pkg/e.py", "symbol": f"K.{name}(field)", "new_name": "column"} for name in ("__init__", "__new__")]
    root = write_project(tmp_path / "p", {"pkg/e.py": BOTH, "map.yaml": yaml.safe_dump(entries)})
    code, _out, err = run(root, ["--apply", "rename-map", "map.yaml"], monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/e.py") == BOTH_RENAMED


def test_another_class_renamed_apart_leaves_a_pair_renamed_alike_linked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    other = "\n\nclass L:\n    def __init__(self, *, field: str) -> None:\n        self.value = field\n"
    entries = [{"file": "pkg/e.py", "symbol": "L.__init__(field)", "new_name": "other"},
               *({"file": "pkg/e.py", "symbol": f"K.{name}(field)", "new_name": "column"} for name in ("__init__", "__new__"))]
    root = write_project(tmp_path / "p", {"pkg/e.py": BOTH + other, "map.yaml": yaml.safe_dump(entries)})
    code, _out, err = run(root, ["--apply", "rename-map", "map.yaml"], monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/e.py") == BOTH_RENAMED + other.replace("field", "other")


def test_a_map_renaming_both_constructors_apart_lists_the_class_call_keyword(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    entries = [{"file": "pkg/e.py", "symbol": "K.__init__(field)", "new_name": "column"},
               {"file": "pkg/e.py", "symbol": "K.__new__(field)", "new_name": "other"}]
    root = write_project(tmp_path / "p", {"pkg/e.py": BOTH, "map.yaml": yaml.safe_dump(entries)})
    before = file_tree(root)
    code, out, err = run(root, ["--apply", "rename-map", "map.yaml"], monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert message("refactor.unlinked-keyword", path="pkg/e.py", line=10, callee="K", old="field") in err.splitlines()
    assert file_tree(root) == before


UNRESOLVED_BOTH = """\
from typing import overload


class K:
    def __new__(cls, *, field: str | int) -> "K":
        return super().__new__(cls)

    @overload
    def __init__(self, *, field: str) -> None: ...
    @overload
    def __init__(self, *, field: int) -> None: ...
    def __init__(self, *, field: str | int) -> None:
        self.value = field


def use() -> K:
    return K(field="a")
"""


@pytest.mark.parametrize("constructor", ["__new__", "__init__"])
def test_a_keyword_the_checker_resolves_to_neither_constructor_is_unlinked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], constructor: str
) -> None:
    root = write_project(tmp_path / "p", {"pkg/e.py": UNRESOLVED_BOTH})
    before = file_tree(root)
    code, out, err = run(root, _rename(f"K.{constructor}(field)"), monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert err.splitlines() == [
        message("refactor.unlinked-keyword", path="pkg/e.py", line=17, callee="K", old="field"),
        message("refactor.blindspots", count=1, names="field="),
    ]
    assert file_tree(root) == before
