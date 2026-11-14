"""Field renames of keyed classes (Pydantic models, TypedDicts): keyword arguments and typed dict keys."""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

import pytest
from project_files import file_tree, write_project

from living_architecture.cli import dr_refactor
from living_architecture.contract import message

MakeProject = Callable[..., Path]

MODELS = """\
from typing import Optional, Sequence, TypedDict

from pydantic import BaseModel


class Member(BaseModel):
    name: str = ""
    type: str = "STR"


class Model(BaseModel):
    columns: list[Member] = []
    label: Optional[str] = None


class Sub(Model):
    extra: int = 0


class Other(BaseModel):
    columns: list[int] = []


class Holder(BaseModel):
    by_name: dict[str, Member] = {}
    maybe: Optional[Member] = None
    seq: Sequence[Member] = ()
    tup: tuple[Member, ...] = ()
    group: set[Member] = set()
    frozen: frozenset[Member] = frozenset()
    model: Model | None = None


class ModelDict(TypedDict):
    columns: list[int]
"""

ALIASED = """\
from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    columns: list[int] = Field(default=[], alias="cols")


class Gen(BaseModel):
    model_config = ConfigDict(alias_generator=str.upper)
    columns: list[int] = []


class Val(BaseModel):
    columns: list[int] = Field(default=[], validation_alias="cols")


class Same(BaseModel):
    columns: list[int] = Field(default=[], alias="columns")
"""

LEGACY = """\
from typing import Any

from pydantic import BaseModel, model_validator


class Model(BaseModel):
    columns: list[int] = []

    @model_validator(mode="before")
    @classmethod
    def migrate(cls, data: Any) -> Any:
        if isinstance(data, dict) and "cols" in data:
            data = {**data, "columns": data.pop("cols")}
        return data
"""


def _field_offset(text: str, owner: str, field: str) -> int:
    return text.index(f"    {field}:", text.index(f"class {owner}(")) + 4


def _declares(cls: ast.ClassDef, field: str) -> int | None:
    for node in cls.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == field:
            return node.lineno
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == field:
            return node.lineno
    return None


def _without_unrelated(root: Path, owner: str, field: str) -> list[str]:
    """`--without` for every class declaring `field` outside `owner`'s hierarchy, as the stand-in check requires."""
    classes = [
        (rel, node)
        for rel in ("pkg/models.py", "pkg/use.py")
        if (root / rel).is_file()
        for node in ast.walk(ast.parse((root / rel).read_text(encoding="utf-8")))
        if isinstance(node, ast.ClassDef)
    ]
    bases = {node.name: {b.id for b in node.bases if isinstance(b, ast.Name)} for _, node in classes}
    related = {owner}
    while (grown := related | {n for n, of in bases.items() if of & related}
           | {b for n in related for b in bases.get(n, ())}) != related:
        related = grown
    flags: list[str] = []
    for rel, node in classes:
        line = _declares(node, field)
        if line is not None and node.name not in related:
            flags += ["--without", f"{rel}:{line}"]
    return flags


def _rename_field(root: Path, owner: str, field: str, new_name: str) -> int:
    path = root / "pkg" / "models.py"
    offset = _field_offset(path.read_text(encoding="utf-8"), owner, field)
    return dr_refactor(["--project", str(root), "--apply", "rename", "--file", str(path), "--offset", str(offset),
                        "--new-name", new_name, *_without_unrelated(root, owner, field)])


def _use_after(typed_project: MakeProject, use: str, owner: str = "Model", field: str = "columns",
               new_name: str = "fields", models: str = MODELS) -> str:
    root = typed_project({"pkg/models.py": models, "pkg/use.py": use})
    assert _rename_field(root, owner, field, new_name) == 0
    return (root / "pkg" / "use.py").read_text(encoding="utf-8")


def test_model_validate_unpacked_dicts_and_subclasses(typed_project: MakeProject) -> None:
    use = (
        "from pkg.models import Model, Sub\n\n"
        'a = Model.model_validate({"columns": []})\n'
        "b = Model(**{'columns': []})\n"
        'c = Sub.model_validate({"columns": [], "extra": 1})\n'
        'd = Model.model_construct(**{"columns": []})\n'
    )
    assert _use_after(typed_project, use) == use.replace("columns", "fields")


def test_the_owner_module_changes_only_at_the_renamed_field(typed_project: MakeProject) -> None:
    root = typed_project({"pkg/models.py": MODELS})
    assert _rename_field(root, "Model", "columns", "fields") == 0
    assert (root / "pkg" / "models.py").read_text(encoding="utf-8") == MODELS.replace(
        "    columns: list[Member] = []", "    fields: list[Member] = []"
    )


def test_cls_in_a_classmethod_and_model_construct(typed_project: MakeProject) -> None:
    use = (
        "from pkg.models import Model\n\n\n"
        "class Model2(Model):\n"
        "    @classmethod\n"
        '    def make(cls) -> "Model2":\n'
        "        return cls(columns=[])\n\n"
        "    @classmethod\n"
        '    def parse(cls) -> "Model2":\n'
        '        return cls.model_validate({"columns": []})\n\n'
        "    @classmethod\n"
        '    def unpack(cls) -> "Model2":\n'
        '        return cls(**{"columns": []})\n\n\n'
        "m = Model.model_construct(columns=[])\n"
    )
    assert _use_after(typed_project, use) == use.replace("columns", "fields")


def test_model_copy_and_model_dump(typed_project: MakeProject) -> None:
    use = (
        "from pkg.models import Model\n\n\n"
        "def f(m: Model) -> object:\n"
        "    return (\n"
        '        m.model_copy(update={"columns": []}),\n'
        '        m.model_dump(exclude={"columns"}),\n'
        '        m.model_dump_json(include={"columns": True, "label": True}),\n'
        "    )\n"
    )
    assert _use_after(typed_project, use) == use.replace("columns", "fields")


def test_nested_member_dicts_through_field_types(typed_project: MakeProject) -> None:
    use = (
        "from pkg.models import Holder, Model\n\n"
        'a = Model.model_validate({"columns": [{"name": "a", "type": "INT"}]})\n'
        'b = Model(columns=[{"type": "INT"}])\n'
        "c = Holder.model_validate({\n"
        '    "by_name": {"x": {"type": "INT"}},\n'
        '    "maybe": {"type": "INT"},\n'
        '    "seq": [{"type": "INT"}],\n'
        '    "tup": ({"type": "INT"},),\n'
        '    "group": [{"type": "INT"}],\n'
        '    "frozen": [{"type": "INT"}],\n'
        '    "model": {"columns": [{"type": "INT"}]},\n'
        "})\n"
    )
    after = _use_after(typed_project, use, owner="Member", field="type", new_name="kind")
    assert after == use.replace('"type"', '"kind"')


def test_typeddict_flows(typed_project: MakeProject) -> None:
    use = (
        "from pkg.models import ModelDict\n\n\n"
        "def f(d: ModelDict) -> None: ...\n\n\n"
        "def g() -> ModelDict:\n"
        '    return {"columns": []}\n\n\n'
        'f({"columns": []})\n'
        'x: ModelDict = {"columns": []}\n'
    )
    root = typed_project({"pkg/models.py": MODELS, "pkg/use.py": use})
    assert _rename_field(root, "ModelDict", "columns", "fields") == 0
    assert (root / "pkg" / "use.py").read_text(encoding="utf-8") == use.replace("columns", "fields")
    assert (root / "pkg" / "models.py").read_text(encoding="utf-8") == MODELS.replace(
        "    columns: list[int]\n", "    fields: list[int]\n"
    )


@pytest.mark.parametrize(
    "sink",
    ["Model.model_validate(raw)", "Sub(**raw)", "Model.model_construct(**raw)", "m.model_copy(update=raw)"],
    ids=["model-validate", "unpacked", "model-construct", "model-copy"],
)
def test_dict_variable_bound_once(typed_project: MakeProject, sink: str) -> None:
    use = (
        "from pkg.models import Model, Sub\n\n\n"
        "def f(m: Model) -> Model:\n"
        '    raw = {"columns": []}\n'
        f"    return {sink}\n"
    )
    assert _use_after(typed_project, use) == use.replace("columns", "fields")


def test_legacy_fixture_behind_a_before_validator_is_rewritten(typed_project: MakeProject) -> None:
    use = 'from pkg.models import Model\n\na = Model.model_validate({"columns": [1]})\n'
    root = typed_project({"pkg/models.py": LEGACY, "pkg/use.py": use})
    assert _rename_field(root, "Model", "columns", "fields") == 0
    assert (root / "pkg" / "use.py").read_text(encoding="utf-8") == use.replace("columns", "fields")
    assert (root / "pkg" / "models.py").read_text(encoding="utf-8") == LEGACY.replace(
        "    columns: list[int] = []", "    fields: list[int] = []"
    )


@pytest.mark.parametrize(
    "body",
    [
        '    raw = {"columns": []}\n    print(raw["columns"])\n    return Model.model_validate(raw)\n',
        '    raw = {"columns": []}\n    raw["label"] = None\n    return Model.model_validate(raw)\n',
        '    raw = {"columns": []}\n    alias = raw\n    return Model.model_validate(alias)\n',
        '    raw = {"columns": []}\n    g = lambda: raw\n    return Model.model_validate(raw)\n',
        '    raw = {"columns": []}\n    other = {**raw}\n    return Model.model_validate(raw)\n',
        '    raw = {"columns": []}\n    raw |= {}\n    return Model.model_validate(raw)\n',
        '    raw = {"columns": []}\n    m = Model.model_validate(raw)\n    del raw\n    return m\n',
        '    raw = {"columns": []}\n    raw = {"columns": []}\n    return Model.model_validate(raw)\n',
        '    raw = {"columns": []}\n\n    def g() -> None:\n        nonlocal raw\n\n    return Model.model_validate(raw)\n',
    ],
    ids=["read", "mutated", "aliased", "captured", "unpacked", "augmented", "deleted", "rebound", "nonlocal"],
)
def test_dict_variable_with_another_use(typed_project: MakeProject, body: str) -> None:
    use = f"from pkg.models import Model\n\n\ndef f() -> Model:\n{body}"
    assert _use_after(typed_project, use) == use


def test_dict_variable_declared_global(typed_project: MakeProject) -> None:
    use = (
        "from pkg.models import Model\n\n"
        'raw = {"columns": []}\n\n\n'
        "def f() -> Model:\n"
        "    global raw\n"
        "    return Model.model_validate(raw)\n"
    )
    assert _use_after(typed_project, use) == use


def test_untyped_and_ambiguous_targets(typed_project: MakeProject) -> None:
    use = (
        "from typing import Any, TypeVar\n\n"
        "from pkg.models import Model, Other\n\n"
        'T = TypeVar("T")\n\n\n'
        "def a(u: Any, v) -> object:\n"
        '    return u.model_validate({"columns": []}), v.model_validate({"columns": []})\n\n\n'
        "def h(d: dict[str, Any]) -> None: ...\n\n\n"
        "def b(m: Model | Other) -> object:\n"
        '    return m.model_copy(update={"columns": []})\n\n\n'
        "def c(kind: type[T]) -> T:\n"
        '    return kind(**{"columns": []})\n\n\n'
        'h({"columns": []})\n'
    )
    assert _use_after(typed_project, use) == use


def test_same_named_field_of_another_class_and_a_typeddict(typed_project: MakeProject) -> None:
    use = (
        "from pkg.models import ModelDict, Other\n\n"
        'a = Other.model_validate({"columns": []})\n'
        "b = Other(columns=[])\n"
        't: ModelDict = {"columns": []}\n'
    )
    assert _use_after(typed_project, use) == use


def test_rebound_cls_and_unrelated_model_construct(typed_project: MakeProject) -> None:
    use = (
        "from pkg.models import Model, Other\n\n\n"
        "class Model2(Model):\n"
        "    @classmethod\n"
        "    def make(cls) -> object:\n"
        "        cls = Other\n"
        "        return cls(columns=[])\n\n\n"
        "class Plain:\n"
        "    @classmethod\n"
        '    def model_construct(cls, columns: list[int]) -> "Plain":\n'
        "        return cls()\n\n\n"
        "p = Plain.model_construct(columns=[])\n"
    )
    assert _use_after(typed_project, use) == use


@pytest.mark.parametrize("owner", ["Model", "Gen", "Val"], ids=["alias", "alias-generator", "validation-alias"])
def test_aliased_field_keys_are_unchanged(typed_project: MakeProject, owner: str) -> None:
    use = f'from pkg.models import {owner}\n\na = {owner}.model_validate({{"columns": []}})\n'
    assert _use_after(typed_project, use, owner=owner, models=ALIASED) == use


def test_aliased_field_keywords_are_unchanged(typed_project: MakeProject) -> None:
    use = (
        "from pkg.models import Same\n\n\n"
        "class Sub(Same):\n"
        "    @classmethod\n"
        '    def make(cls) -> "Sub":\n'
        "        return cls(columns=[])\n\n\n"
        "m = Same.model_construct(columns=[])\n"
    )
    assert _use_after(typed_project, use, owner="Same", models=ALIASED) == use


def test_typeddict_named_dicts_returned_and_assigned(typed_project: MakeProject) -> None:
    use = (
        "from pkg.models import ModelDict\n\n\n"
        "def g() -> ModelDict:\n"
        '    data = {"columns": []}\n'
        "    return data\n\n\n"
        "def h() -> None:\n"
        '    data = {"columns": []}\n'
        "    x: ModelDict = data\n"
    )
    assert _use_after(typed_project, use, owner="ModelDict") == use.replace("columns", "fields")


def test_typeddict_arguments_bind_only_proven_parameters(typed_project: MakeProject) -> None:
    use = (
        "from pkg.models import ModelDict\n\n\n"
        "class Service:\n"
        "    def take(self, payload: ModelDict, metadata: dict) -> None: ...\n\n"
        "    @staticmethod\n"
        "    def check(payload: ModelDict) -> None: ...\n\n"
        "    @classmethod\n"
        "    def make(cls, payload: ModelDict) -> None: ...\n\n"
        "    def run(self) -> None:\n"
        '        self.take({"columns": 9}, {"columns": 10})\n\n\n'
        "def take(prefix: object, payload: ModelDict, metadata: dict) -> None: ...\n\n\n"
        "def use(svc: Service) -> None:\n"
        '    svc.take({"columns": 11}, {"columns": 12})\n'
        '    Service.take(svc, {"columns": 13}, {"columns": 14})\n\n\n'
        "s = Service()\n"
        's.take({"columns": 1}, {"columns": 2})\n'
        's.take(payload={"columns": 3}, metadata={"columns": 4})\n'
        'Service.check({"columns": 5})\n'
        'Service.make({"columns": 6})\n'
        'take(*(0, {"columns": 7}), {"columns": 8})\n'
    )
    expected = use
    for n in (3, 5, 6, 9, 11, 13):
        expected = expected.replace(f'{{"columns": {n}}}', f'{{"fields": {n}}}')
    assert _use_after(typed_project, use, owner="ModelDict") == expected


def test_typeddict_arguments_follow_resolved_decorators(typed_project: MakeProject) -> None:
    use = (
        "import builtins\n"
        "import functools\n\n"
        "from typing_extensions import override\n\n"
        "from pkg.models import ModelDict\n\n\n"
        "class Base:\n"
        "    def run(self, payload: ModelDict) -> None: ...\n\n\n"
        "class Service(Base):\n"
        "    @builtins.staticmethod\n"
        "    def take(prefix: dict, payload: ModelDict) -> None: ...\n\n"
        "    @builtins.classmethod\n"
        "    def make(cls, payload: ModelDict) -> None: ...\n\n"
        "    @override\n"
        "    def run(self, payload: ModelDict) -> None: ...\n\n"
        "    @functools.cache\n"
        "    def cached(self, payload: ModelDict) -> None: ...\n\n\n"
        "def use(svc: Service) -> None:\n"
        '    svc.take({"columns": 0}, {"columns": 1})\n'
        '    svc.make({"columns": 2})\n'
        '    svc.run({"columns": 3})\n'
        '    svc.cached({"columns": 4})\n'
    )
    expected = use
    for n in (1, 2, 3):
        expected = expected.replace(f'{{"columns": {n}}}', f'{{"fields": {n}}}')
    assert _use_after(typed_project, use, owner="ModelDict") == expected


def test_module_level_dict_variable_is_unchanged(typed_project: MakeProject) -> None:
    use = 'from pkg.models import Model\n\nraw = {"columns": []}\nm = Model.model_validate(raw)\n'
    root = typed_project({
        "pkg/models.py": MODELS, "pkg/use.py": use, "pkg/reader.py": 'from pkg.use import raw\n\nprint(raw["columns"])\n'
    })
    assert _rename_field(root, "Model", "columns", "fields") == 0
    assert (root / "pkg" / "use.py").read_text(encoding="utf-8") == use


def test_only_plain_key_literals_change_and_only_their_name(typed_project: MakeProject) -> None:
    use = (
        "from pkg.models import Model\n\n"
        'a = Model.model_validate({"col" "umns": []})\n'
        'b = Model.model_validate({"\\x63olumns": []})\n'
        'c = Model.model_validate({f"columns": []})\n'
        "d = Model.model_validate({r'columns': []})\n"
    )
    assert _use_after(typed_project, use) == use.replace("r'columns'", "r'fields'")


@pytest.mark.parametrize(
    "line",
    ['a = Model.model_validate({"columns": [], "fields": []})\n', "b = Model(columns=[], fields=[])\n"],
    ids=["key", "keyword"],
)
def test_key_or_keyword_collision(
    typed_project: MakeProject, capsys: pytest.CaptureFixture[str], line: str
) -> None:
    root = typed_project({"pkg/models.py": MODELS, "pkg/use.py": f"from pkg.models import Model\n\n{line}"})
    before = file_tree(root)
    assert _rename_field(root, "Model", "columns", "fields") == 1
    err = capsys.readouterr().err
    assert err == message("refactor.name-conflict", name="fields", path="pkg/use.py", line=3) + "\n"
    assert file_tree(root) == before


UNRESOLVED = (
    "from pydantic import BaseModel\n\n\n"
    "class Model(BaseModel):\n"
    "    columns: list[int] = []\n\n"
    "    def describe(self) -> str:\n"
    '        return ""\n'
)


@pytest.fixture
def without_pydantic(tmp_path: Path) -> Path:
    """A project whose configured environment lacks pydantic."""
    root = write_project(tmp_path / "proj", {
        "pkg/models.py": UNRESOLVED,
        "pkg/use.py": 'from pkg.models import Model\n\na = Model.model_validate({"columns": []})\nb = Model(columns=[])\n',
        "pyproject.toml": '[tool.basedpyright]\nvenvPath = "."\nvenv = "env"\n',
        "env/pyvenv.cfg": "home = /usr/bin\nversion = 3.11.0\n",
        "env/lib/python3.11/site-packages/.keep": "",
    }, venv=False)
    return root


def test_field_rename_refuses_an_unresolved_owner_chain(
    without_pydantic: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = file_tree(without_pydantic)
    assert _rename_field(without_pydantic, "Model", "columns", "fields") == 1
    err = capsys.readouterr().err
    assert err == message("refactor.unresolved-base", name="Model", path="pkg/models.py", line=4) + "\n"
    assert file_tree(without_pydantic) == before


def test_field_rename_refuses_a_base_expression(typed_project: MakeProject, capsys: pytest.CaptureFixture[str]) -> None:
    models = MODELS + (
        "\n\ndef make_base() -> type[BaseModel]:\n"
        "    return BaseModel\n\n\n"
        "class Child(make_base(), Model):\n"
        "    pass\n"
    )
    root = typed_project({"pkg/models.py": models, "pkg/use.py": "from pkg.models import Child\n\nc = Child(columns=[])\n"})
    before = file_tree(root)
    assert _rename_field(root, "Model", "columns", "fields") == 1
    line = models[: models.index("class Child(")].count("\n") + 1
    err = capsys.readouterr().err
    assert err == message("refactor.unresolved-base", name="Child", path="pkg/models.py", line=line) + "\n"
    assert file_tree(root) == before


def test_unresolved_base_outside_the_project_names_its_absolute_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ext = tmp_path / "ext" / "extlib.py"
    ext.parent.mkdir()
    ext.write_text("from missing_lib import Base\n\n\nclass Ext(Base):\n    pass\n", encoding="utf-8")
    root = write_project(tmp_path / "proj", {
        "pkg/models.py": "from extlib import Ext\n\n\nclass Model(Ext):\n    columns: list[int] = []\n",
    })
    with open(root / "pyproject.toml", "a", encoding="utf-8") as fh:
        fh.write('extraPaths = ["../ext"]\n')
    assert _rename_field(root, "Model", "columns", "fields") == 1
    err = capsys.readouterr().err
    assert err == message("refactor.unresolved-base", name="Ext", path=ext.resolve().as_posix(), line=4) + "\n"


def test_method_rename_proceeds_with_an_unresolved_base(without_pydantic: Path) -> None:
    path = without_pydantic / "pkg" / "models.py"
    offset = UNRESOLVED.index("describe")
    assert dr_refactor(["--project", str(without_pydantic), "--apply", "rename", "--file", str(path),
                        "--offset", str(offset), "--new-name", "summary"]) == 0
    assert path.read_text(encoding="utf-8") == UNRESOLVED.replace("describe", "summary")
