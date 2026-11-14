"""Python renames rewrite members named by string: receiver forms and dotted patch targets."""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

import pytest
from project_files import file_tree

from living_architecture.cli import dr_refactor
from living_architecture.contract import message
from living_architecture.lang import Span
from living_architecture.refactor.member_scan import FormCall, Probe, plain_literal
from living_architecture.refactor.python_source import SourceFile

MakeProject = Callable[..., Path]

ENGINE = "class SearchQueryEngine:\n    def save_model(self, name: str) -> None:\n        pass\n"
REEXPORT = "from pkg.engine import SearchQueryEngine\n\n__all__ = [\"SearchQueryEngine\"]\n"

RECEIVER_FORMS = """\
from unittest.mock import patch

import pytest
from pytest_mock import MockerFixture

from pkg.engine import SearchQueryEngine


class Sub(SearchQueryEngine):
    pass


def test_forms(engine: SearchQueryEngine, sub: Sub, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture) -> None:
    patch.object(SearchQueryEngine, "save_model")
    monkeypatch.setattr(engine, "save_model", lambda name: None)
    mocker.patch.object(engine, 'save_model')
    getattr(engine, "save_model")
    setattr(sub, "save_model", None)
    hasattr(type(engine), "save_model")
    delattr(Sub, "save_model")
    monkeypatch.delattr(SearchQueryEngine, "save_model")
    mocker.patch.object(Sub, "save_model", autospec=True)
"""

NOT_FORMS = """\
from pkg.engine import SearchQueryEngine


def f(engine: SearchQueryEngine) -> None:
    getattr(engine, f"save_model")
    getattr(engine, "save_" "model")
    getattr(engine, "save_model_x")
    getattr(engine, "save_model", None)
    print("save_model")
"""

OTHER = "class Other:\n    def save_model(self) -> None:\n        pass\n"

LOOKALIKES = """\
from pkg.engine import SearchQueryEngine


class Cfg:
    def setattr(self, o: object, n: str) -> None: ...


def getattr(o: object, n: str) -> object:
    return o


def f(engine: SearchQueryEngine, cfg: Cfg) -> None:
    getattr(engine, "save_model")
    cfg.setattr(engine, "save_model")
"""

TARGETS = """\
from unittest.mock import patch

import pytest
from pytest_mock import MockerFixture


def test_targets(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    patch("pkg.engine.SearchQueryEngine.save_model")
    patch("pkg.SearchQueryEngine.save_model")
    mocker.patch("pkg.engine.SearchQueryEngine.save_model")
    monkeypatch.setattr("pkg.engine.SearchQueryEngine.save_model", None)
    monkeypatch.delattr('pkg.SearchQueryEngine.save_model')
"""


@pytest.fixture
def project(typed_project: MakeProject, monkeypatch: pytest.MonkeyPatch) -> MakeProject:
    def make(files: dict[str, str], **kw: object) -> Path:
        root = typed_project(files, **kw)
        monkeypatch.chdir(root)
        return root

    return make


def _rename(root: Path, rel: str, needle: str, new_name: str, *flags: str) -> int:
    offset = (root / rel).read_text(encoding="utf-8").index(needle)
    return dr_refactor(["--project", str(root), "--apply", "rename", "--file", rel, "--offset", str(offset),
                        "--new-name", new_name, *flags])


def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def _rename_save_model(root: Path, *flags: str, file: str = "pkg/engine.py") -> int:
    return _rename(root, file, "save_model", "persist_model", *flags)


def _patch_test(*targets: str) -> str:
    return "from unittest.mock import patch\n\n\ndef test_t() -> None:\n" + "".join(f'    patch("{t}")\n' for t in targets)


def test_receiver_forms_on_instances_and_class_objects(project: MakeProject, capsys: pytest.CaptureFixture[str]) -> None:
    root = project({"pkg/engine.py": ENGINE, "tests/test_engine.py": RECEIVER_FORMS})
    assert _rename_save_model(root) == 0
    assert capsys.readouterr().err == ""
    assert _read(root, "tests/test_engine.py") == RECEIVER_FORMS.replace("save_model", "persist_model")


def test_only_plain_literals_naming_exactly_the_member_change(project: MakeProject) -> None:
    root = project({"pkg/engine.py": ENGINE, "pkg/use.py": NOT_FORMS})
    assert _rename_save_model(root) == 0
    assert _read(root, "pkg/use.py") == NOT_FORMS.replace(
        'getattr(engine, "save_model", None)', 'getattr(engine, "persist_model", None)'
    )


def test_member_of_another_class_is_unchanged(project: MakeProject) -> None:
    use = 'from pkg.other import Other\n\n\ndef f(other: Other) -> object:\n    return getattr(other, "save_model")\n'
    root = project({"pkg/engine.py": ENGINE, "pkg/other.py": OTHER, "pkg/use.py": use})
    assert _rename_save_model(root, "--without", "pkg/other.py:2") == 0
    assert _read(root, "pkg/use.py") == use


def test_lookalike_callees_are_neither_rewritten_nor_blind_spots_but_listed(
    project: MakeProject, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project({"pkg/engine.py": ENGINE, "pkg/use.py": LOOKALIKES})
    assert _rename_save_model(root) == 0
    assert capsys.readouterr().err == "".join(
        message("refactor.leftover", path="pkg/use.py", line=line, where="string", old="save_model") + "\n" for line in (13, 14)
    )
    assert _read(root, "pkg/use.py") == LOOKALIKES


def test_an_untyped_object_is_a_blind_spot(project: MakeProject, capsys: pytest.CaptureFixture[str]) -> None:
    use = 'def f(o) -> object:\n    return getattr(o, "save_model")\n'
    root = project({"pkg/engine.py": ENGINE, "pkg/use.py": use})
    before = file_tree(root)
    assert _rename_save_model(root) == 1
    assert capsys.readouterr().err == (
        message("compliance.attr-blindspot", path="pkg/use.py", line=2, receiver="o", attr="save_model", type="Unknown")
        + "\n" + message("refactor.blindspots", count=1, attr="save_model") + "\n"
    )
    assert file_tree(root) == before


# ---- dotted patch targets


def test_dotted_patch_targets_through_modules_and_re_exports(project: MakeProject) -> None:
    root = project({"pkg/__init__.py": REEXPORT, "pkg/engine.py": ENGINE, "tests/test_patch.py": TARGETS})
    assert _rename_save_model(root) == 0
    assert _read(root, "tests/test_patch.py") == TARGETS.replace("save_model", "persist_model")


def test_class_rename_rewrites_its_target_segment(project: MakeProject) -> None:
    root = project({"pkg/__init__.py": REEXPORT, "pkg/engine.py": ENGINE, "tests/test_patch.py": TARGETS})
    assert _rename(root, "pkg/engine.py", "SearchQueryEngine", "QueryEngine") == 0
    assert _read(root, "tests/test_patch.py") == TARGETS.replace("SearchQueryEngine", "QueryEngine")


def test_function_rename_rewrites_its_target_segment(project: MakeProject) -> None:
    util = "def helper() -> int:\n    return 1\n"
    test = 'from unittest.mock import patch\n\n\ndef test_h() -> None:\n    patch("pkg.util.helper")\n'
    root = project({"pkg/util.py": util, "tests/test_util.py": test})
    assert _rename(root, "pkg/util.py", "helper", "assist") == 0
    assert _read(root, "tests/test_util.py") == test.replace("helper", "assist")


def test_a_target_naming_another_member_is_unchanged(project: MakeProject) -> None:
    test = _patch_test("pkg.other.Other.save_model", "pkg.engine.SearchQueryEngine.save_model_x")
    root = project({"pkg/engine.py": ENGINE, "pkg/other.py": OTHER, "tests/test_t.py": test})
    assert _rename_save_model(root, "--without", "pkg/other.py:2") == 0
    assert _read(root, "tests/test_t.py") == test


UNRESOLVED = _patch_test("pkg.engine.Missing.save_model", "thirdparty.mod.save_model")


def test_an_unresolved_project_target_is_a_blind_spot(
    project: MakeProject, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project({"pkg/engine.py": ENGINE, "tests/test_t.py": UNRESOLVED})
    before = file_tree(root)
    assert _rename_save_model(root) == 1
    assert capsys.readouterr() == ("", (
        message("refactor.unresolved-target", path="tests/test_t.py", line=5,
                target="pkg.engine.Missing.save_model", attr="save_model")
        + "\n" + message("refactor.blindspots", count=1, attr="save_model") + "\n"
    ))
    assert file_tree(root) == before


def test_an_external_target_is_a_leftover(project: MakeProject, capsys: pytest.CaptureFixture[str]) -> None:
    root = project({"pkg/engine.py": ENGINE, "tests/test_t.py": UNRESOLVED})
    assert _rename_save_model(root, "--allow-blindspots") == 0
    err = capsys.readouterr().err.splitlines()
    assert message("refactor.unresolved-target", path="tests/test_t.py", line=5,
                   target="pkg.engine.Missing.save_model", attr="save_model") in err
    assert message("refactor.leftover", path="tests/test_t.py", line=6, where="patch target", old="save_model") in err
    assert _read(root, "tests/test_t.py") == UNRESOLVED


def test_a_kept_unresolved_target_does_not_block(project: MakeProject) -> None:
    root = project({"pkg/engine.py": ENGINE, "tests/test_t.py": UNRESOLVED})
    assert _rename_save_model(root, "--keep", "tests/test_t.py:5") == 0
    assert _read(root, "pkg/engine.py") == ENGINE.replace("save_model", "persist_model")


@pytest.mark.parametrize("engine", ["src/pkg/engine.py", "src/pkg/sub/engine.py"], ids=["package", "no-init-below"])
def test_target_from_tests_into_a_src_layout(project: MakeProject, engine: str) -> None:
    module = engine.removeprefix("src/").removesuffix(".py").replace("/", ".")
    test = _patch_test(f"{module}.SearchQueryEngine.save_model")
    root = project({"src/pkg/__init__.py": "", engine: ENGINE, "tests/test_t.py": test}, package=False)
    assert _rename_save_model(root, file=engine) == 0
    assert _read(root, "tests/test_t.py") == test.replace("save_model", "persist_model")


INHERIT = """\
class Base:
    def save_model(self) -> None:
        pass


class Sub(Base):
    pass


class Over(Base):
    def save_model(self) -> None:
        pass
"""

DIAMOND = """\
class Base:
    def save_model(self) -> None:
        pass


class L(Base):
    pass


class R(Base):
    def save_model(self) -> None:
        pass


class D(L, R):
    pass
"""


@pytest.mark.parametrize(
    ("engine", "classes", "flags", "renamed"),
    [
        pytest.param(INHERIT, ["Sub", "Over"], [], ["Sub", "Over"], id="inherited-and-overridden"),
        pytest.param(INHERIT, ["Sub", "Over"], ["--no-in-hierarchy"], ["Sub"], id="overridden-outside-the-rename"),
        pytest.param(DIAMOND, ["L", "D"], [], ["L", "D"], id="diamond"),
        pytest.param(DIAMOND, ["L", "D"], ["--no-in-hierarchy"], ["L"], id="diamond-follows-c3-order"),
    ],
)
def test_target_through_inheritance(
    project: MakeProject, engine: str, classes: list[str], flags: list[str], renamed: list[str]
) -> None:
    test = _patch_test(*(f"pkg.engine.{cls}.save_model" for cls in classes))
    root = project({"pkg/engine.py": engine, "tests/test_t.py": test})
    assert _rename_save_model(root, *flags) == 0
    expected = test
    for cls in renamed:
        expected = expected.replace(f"pkg.engine.{cls}.save_model", f"pkg.engine.{cls}.persist_model")
    assert _read(root, "tests/test_t.py") == expected


def test_target_override_in_a_class_level_block_shadows_the_base(project: MakeProject) -> None:
    engine = (
        "class Base:\n    def save_model(self) -> None:\n        pass\n\n\n"
        "class Child(Base):\n    if True:\n        def save_model(self) -> None:\n            pass\n"
    )
    test = _patch_test("pkg.engine.Child.save_model")
    root = project({"pkg/engine.py": engine, "tests/test_t.py": test})
    assert _rename_save_model(root, "--no-in-hierarchy") == 0
    assert _read(root, "tests/test_t.py") == test


def test_target_through_a_star_import_honouring_all(project: MakeProject) -> None:
    test = _patch_test("pkg.api.SearchQueryEngine.save_model")
    root = project({
        "pkg/engine.py": ENGINE + '\n__all__ = ["SearchQueryEngine"]\n',
        "pkg/api.py": "from pkg.engine import *\n",
        "tests/test_t.py": test,
    })
    assert _rename_save_model(root) == 0
    assert _read(root, "tests/test_t.py") == test.replace("save_model", "persist_model")


BASES = """\


class Blocked(Mixin, SearchQueryEngine):
    pass


class Reached(SearchQueryEngine, Mixin):
    pass
"""


@pytest.mark.parametrize(
    ("files", "engine", "targets", "refused"),
    [
        pytest.param(
            {"src/pkg/__init__.py": "", "src/pkg/engine.py": ENGINE,
             "lib/pkg/__init__.py": "", "lib/pkg/engine.py": "VALUE = 1\n"},
            "src/pkg/engine.py", ["pkg.engine.SearchQueryEngine.save_model"], ["pkg.engine.SearchQueryEngine.save_model"],
            id="module-in-two-source-folders",
        ),
        pytest.param(
            {"pkg/engine.py": ENGINE, "pkg/legacy.py": "class SearchQueryEngine:\n    pass\n",
             "pkg/api.py": "try:\n    from pkg.engine import SearchQueryEngine\nexcept ImportError:\n"
                           "    from pkg.legacy import SearchQueryEngine\n"},
            "pkg/engine.py", ["pkg.api.SearchQueryEngine.save_model"], ["pkg.api.SearchQueryEngine.save_model"],
            id="conflicting-bindings",
        ),
        pytest.param(
            {"pkg/engine.py": ENGINE + '\n__all__ = ["VERSION"]\nVERSION = 1\n', "pkg/api.py": "from pkg.engine import *\n"},
            "pkg/engine.py", ["pkg.api.SearchQueryEngine.save_model"], ["pkg.api.SearchQueryEngine.save_model"],
            id="star-import-excluded-by-all",
        ),
        pytest.param(
            {"pkg/engine.py": ENGINE, "pkg/a.py": "from pkg.b import SearchQueryEngine\n",
             "pkg/b.py": "from pkg.a import SearchQueryEngine\n"},
            "pkg/engine.py", ["pkg.a.SearchQueryEngine.save_model"], ["pkg.a.SearchQueryEngine.save_model"],
            id="import-cycle",
        ),
        pytest.param(
            {"pkg/engine.py": "from pkg.missing import Mixin\n\n\n" + ENGINE + BASES},
            "pkg/engine.py", ["pkg.engine.Blocked.save_model", "pkg.engine.Reached.save_model"],
            ["pkg.engine.Blocked.save_model"],
            id="unresolved-base-before-the-attribute",
        ),
    ],
)
def test_ambiguous_targets_refuse(
    project: MakeProject,
    capsys: pytest.CaptureFixture[str],
    files: dict[str, str],
    engine: str,
    targets: list[str],
    refused: list[str],
) -> None:
    test = _patch_test(*targets)
    root = project({**files, "tests/test_t.py": test}, package="pkg/engine.py" in files)
    before = file_tree(root)
    assert _rename_save_model(root, file=engine) == 1
    lines = [
        message("refactor.unresolved-target", path="tests/test_t.py", line=5 + targets.index(target), target=target,
                attr="save_model")
        for target in refused
    ]
    expected = "".join(f"{line}\n" for line in [*lines, message("refactor.blindspots", count=len(refused), attr="save_model")])
    assert capsys.readouterr() == ("", expected)
    assert file_tree(root) == before


def test_resolving_targets_runs_no_project_code(
    typed_project: MakeProject, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    marker = tmp_path / "MARKER"
    side_effect = f"import pathlib\npathlib.Path({str(marker)!r}).write_text('ran')\n"
    root = typed_project({
        "sitecustomize.py": side_effect,
        "pkg/__init__.py": side_effect + REEXPORT,
        "pkg/engine.py": side_effect + ENGINE,
        "tests/test_patch.py": TARGETS,
    }, venv=False)
    monkeypatch.chdir(root)
    assert _rename_save_model(root, "--allow-blindspots") == 0
    assert not marker.exists()


# ---- the probe: its text and the map back to the file's own offsets

PROBED = 'a = 1\nx = getattr(eng, "save_model")\nb = 2\ny = getattr(eng.inner,  "save_model")\nc = 3\n'


def _calls(source: SourceFile) -> list[FormCall]:
    assert source.tree is not None
    calls = [n for n in ast.walk(source.tree) if isinstance(n, ast.Call)]
    out: list[FormCall] = []
    for call in calls:
        found = plain_literal(source, call.args[1])
        assert found is not None
        out.append(FormCall(call=call, literal=found[0], text=found[1], obj=call.args[0], forms=()))
    return out


@pytest.mark.parametrize("order", [[0, 1], [1, 0]], ids=["source-order", "reversed"])
def test_probe_text_and_accesses_in_any_call_order(order: list[int]) -> None:
    source = SourceFile(Path("/p/m.py"), PROBED)
    calls = [_calls(source)[i] for i in order]
    probe = Probe(source, calls, "save_model")
    assert probe.text == 'a = 1\nx = getattr(eng, (eng).save_model)\nb = 2\ny = getattr(eng.inner,  (eng.inner).save_model)\nc = 3\n'
    for i, call in enumerate(calls):
        assert call.obj is not None
        prefix = f"({source.segment(call.obj)})."
        assert probe.text[probe.accesses[i] - len(prefix) :].startswith(f"{prefix}save_model")


@pytest.mark.parametrize("name", ["a", "b", "c"], ids=["before", "between", "after"])
def test_probe_maps_a_declaration_back(name: str) -> None:
    source = SourceFile(Path("/p/m.py"), PROBED)
    probe = Probe(source, _calls(source), "save_model")
    at = probe.text.index(f"{name} = ")
    assert probe.original(Span(path=Path("/p/m.py"), start=at, end=at + 1)) == Span(
        path=Path("/p/m.py"), start=PROBED.index(f"{name} = "), end=PROBED.index(f"{name} = ") + 1)


def test_probe_leaves_a_definition_in_another_file() -> None:
    source = SourceFile(Path("/p/m.py"), PROBED)
    probe = Probe(source, _calls(source), "save_model")
    span = Span(path=Path("/p/other.py"), start=40, end=50)
    assert probe.original(span) == span


def test_a_function_rename_lists_no_exact_literal(project: MakeProject, capsys: pytest.CaptureFixture[str]) -> None:
    funcs = 'def save_model() -> None:\n    pass\n\n\nNAME = "save_model"\n'
    root = project({"pkg/funcs.py": funcs})
    offset = funcs.index("save_model")
    assert dr_refactor(["--project", str(root), "rename", "--file", "pkg/funcs.py", "--offset", str(offset),
                        "--new-name", "store_model"]) == 0
    assert capsys.readouterr().err == ""


def test_a_callee_resolves_by_any_spelling_and_syntax_decides_only_when_unresolved(
    project: MakeProject, capsys: pytest.CaptureFixture[str]
) -> None:
    forms = (
        "from builtins import getattr as read\n\n"
        "from pkg.engine import SearchQueryEngine\n\n\n"
        "def getattr(o: object, n: str) -> object:\n"
        "    return o\n\n\n"
        "def f(engine: SearchQueryEngine, mocker) -> None:\n"
        '    read(engine, "save_model")\n'
        '    getattr(engine, "save_model")\n'
        '    mocker.patch.object(engine, "save_model")\n'
    )
    root = project({"pkg/engine.py": ENGINE, "pkg/use.py": forms})
    assert _rename_save_model(root, "--allow-blindspots") == 0
    after = _read(root, "pkg/use.py").splitlines()
    assert after[10:13] == [
        '    read(engine, "persist_model")',
        '    getattr(engine, "save_model")',
        '    mocker.patch.object(engine, "save_model")',
    ]
    err = capsys.readouterr().err.splitlines()
    assert err == [
        message("compliance.attr-blindspot", path="pkg/use.py", line=13, receiver="engine", attr="save_model", type="Unknown"),
        message("refactor.leftover", path="pkg/use.py", line=12, where="string", old="save_model"),
    ]


@pytest.mark.parametrize("docs", [False, True], ids=["plain", "docs"])
def test_a_target_resolving_to_an_unchanged_declaration_is_unchanged_and_unlisted(
    project: MakeProject, capsys: pytest.CaptureFixture[str], docs: bool
) -> None:
    test = _patch_test("pkg.other.Other.save_model")
    root = project({"pkg/engine.py": ENGINE, "pkg/other.py": OTHER, "tests/test_t.py": test})
    assert _rename_save_model(root, "--without", "pkg/other.py:2", *(["--docs"] if docs else [])) == 0
    assert _read(root, "tests/test_t.py") == test
    assert "tests/test_t.py" not in capsys.readouterr().err


def test_a_target_form_with_an_unresolved_callee_is_listed_in_a_class_rename(
    project: MakeProject, capsys: pytest.CaptureFixture[str]
) -> None:
    test = 'def test_t(mocker):\n    mocker.patch("pkg.engine.SearchQueryEngine.save_model")\n'
    root = project({"pkg/engine.py": ENGINE, "tests/test_t.py": test})
    assert _rename(root, "pkg/engine.py", "SearchQueryEngine", "QueryEngine") == 0
    assert _read(root, "tests/test_t.py") == test
    leftover = message("refactor.leftover", path="tests/test_t.py", line=2, where="patch target", old="SearchQueryEngine")
    assert capsys.readouterr().err == f"{leftover}\n"


def test_a_callee_bound_to_a_form_and_to_something_else_is_unresolved(
    project: MakeProject, capsys: pytest.CaptureFixture[str]
) -> None:
    helpers = "def patch(target: str) -> None: ...\n"
    test = (
        "try:\n"
        "    from unittest.mock import patch\n"
        "except ImportError:\n"
        "    from pkg.helpers import patch\n\n\n"
        "def test_t() -> None:\n"
        '    patch("pkg.engine.SearchQueryEngine.save_model")\n'
    )
    root = project({"pkg/engine.py": ENGINE, "pkg/helpers.py": helpers, "tests/test_t.py": test})
    assert _rename_save_model(root) == 1
    unresolved = message("refactor.unresolved-target", path="tests/test_t.py", line=8,
                         target="pkg.engine.SearchQueryEngine.save_model", attr="save_model")
    assert capsys.readouterr().err.splitlines() == [unresolved, message("refactor.blindspots", count=1, attr="save_model")]
    assert _read(root, "tests/test_t.py") == test
