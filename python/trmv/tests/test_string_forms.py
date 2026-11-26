"""The registry's string-named member forms as the Python twin loads them, and the `{site}` text of each form."""

from __future__ import annotations

import ast
import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from trmv.contract import language
from trmv.refactor.member_scan import registry_forms, site_text
from trmv.refactor.python_source import SourceFile

NEW_KEYS: dict[str, list[dict[str, object]]] = {
    "name_decorators": [
        {"call": "pydantic.field_validator", "module": "pydantic.functional_validators", "qualname": "field_validator"},
    ],
    "name_reads": [
        {"attribute": "model_fields", "module": "pydantic.main", "qualname": "BaseModel.model_fields",
         "shapes": ["subscript", "get", "in"]},
    ],
    "name_class_values": [{"name": "__slots__", "shapes": ["element", "string", "key"]}],
}
GETATTR = {"call": "getattr", "module": "builtins", "qualname": "getattr", "syntax": "getattr", "object": 0, "member": 1}


def _section(**entries: object) -> dict[str, Any]:
    """A valid python registry section, each of `entries` replacing the one entry of its key."""
    section: dict[str, Any] = {"string_member_calls": [GETATTR], **copy.deepcopy(NEW_KEYS)}
    for key, entry in entries.items():
        section[key] = [entry]
    return section


def test_a_valid_section_loads_entry_for_entry() -> None:
    forms = registry_forms(_section(string_member_calls={**GETATTR, "default": 2}))
    assert [(f.call, f.silent, f.default) for f in forms.string_member_calls] == [("getattr", False, 2)]
    assert [(d.call, d.module, d.qualname) for d in forms.name_decorators] == [
        ("pydantic.field_validator", "pydantic.functional_validators", "field_validator")
    ]
    assert [(r.attribute, r.module, r.qualname, tuple(r.shapes)) for r in forms.name_reads] == [
        ("model_fields", "pydantic.main", "BaseModel.model_fields", ("subscript", "get", "in"))
    ]
    assert [(v.name, tuple(v.shapes)) for v in forms.name_class_values] == [("__slots__", ("element", "string", "key"))]


def test_the_vendored_registry_loads() -> None:
    forms = registry_forms(language("python"))
    assert [f.call for f in forms.string_member_calls if f.silent] == ["hasattr"]
    assert [(f.call, f.default) for f in forms.string_member_calls if f.default is not None] == [("getattr", 2)]
    assert sorted(d.qualname for d in forms.name_decorators) == ["field_serializer", "field_validator"]
    assert sorted(r.attribute for r in forms.name_reads) == ["model_fields", "model_fields_set"]
    assert sorted(v.name for v in forms.name_class_values) == ["__match_args__", "__slots__"]


def _without(entry: dict[str, object], key: str) -> dict[str, object]:
    return {k: v for k, v in entry.items() if k != key}


DECORATOR, READ, CLASS_VALUE = (NEW_KEYS[key][0] for key in ("name_decorators", "name_reads", "name_class_values"))


@pytest.mark.parametrize(
    ("key", "entry"),
    [
        pytest.param("string_member_calls", {**GETATTR, "silent": [1]}, id="silent-not-a-flag"),
        pytest.param("string_member_calls", {**GETATTR, "default": "last"}, id="default-not-a-position"),
        pytest.param("string_member_calls", {**GETATTR, "sylent": True}, id="call-unknown-key"),
        pytest.param("name_decorators", _without(DECORATOR, "qualname"), id="decorator-without-qualname"),
        pytest.param("name_decorators", _without(DECORATOR, "module"), id="decorator-without-module"),
        pytest.param("name_decorators", "field_validator", id="decorator-not-a-mapping"),
        pytest.param("name_decorators", {**DECORATOR, "syntax": "field_validator"}, id="decorator-unknown-key"),
        pytest.param("name_reads", _without(READ, "attribute"), id="read-without-attribute"),
        pytest.param("name_reads", _without(READ, "shapes"), id="read-without-shapes"),
        pytest.param("name_reads", {**READ, "shapes": ["subscript", "call"]}, id="read-unknown-shape"),
        pytest.param("name_reads", {**READ, "shapes": "subscript"}, id="read-shapes-not-a-list"),
        pytest.param("name_reads", {**READ, "shape": "in"}, id="read-unknown-key"),
        pytest.param("name_class_values", _without(CLASS_VALUE, "name"), id="class-value-without-name"),
        pytest.param("name_class_values", {**CLASS_VALUE, "shapes": ["value"]}, id="class-value-unknown-shape"),
        pytest.param("name_class_values", {**CLASS_VALUE, "qualname": "__slots__"}, id="class-value-unknown-key"),
    ],
)
def test_a_malformed_entry_is_a_contract_error(key: str, entry: object) -> None:
    section = _section(**{key: entry})
    with pytest.raises(ValueError):
        registry_forms(section)


@pytest.mark.parametrize("key", sorted(NEW_KEYS))
def test_a_key_that_is_not_a_list_is_a_contract_error(key: str) -> None:
    section = _section()
    section[key] = {"entries": section[key]}
    with pytest.raises(ValueError):
        registry_forms(section)


# ---- `{site}`

Pick = Callable[[ast.expr], ast.expr]


def _argument(access: ast.expr) -> ast.expr:
    assert isinstance(access, ast.Call)
    return access.args[0]


def _subscripted(access: ast.expr) -> ast.expr:
    assert isinstance(access, ast.Subscript)
    assert isinstance(access.value, ast.Attribute)
    return access.value.value


def _got(access: ast.expr) -> ast.expr:
    assert isinstance(access, ast.Call)
    assert isinstance(access.func, ast.Attribute)
    assert isinstance(access.func.value, ast.Attribute)
    return access.func.value.value


def _container(access: ast.expr) -> ast.expr:
    assert isinstance(access, ast.Compare)
    assert isinstance(access.comparators[0], ast.Attribute)
    return access.comparators[0].value


def _site(text: str, obj: Pick, name: str) -> str:
    source = SourceFile(Path("/proj/m.py"), text)
    assert source.tree is not None
    statement = source.tree.body[0]
    assert isinstance(statement, ast.Expr)
    return site_text(source, statement.value, obj(statement.value), name)


@pytest.mark.parametrize(
    ("text", "site"),
    [
        pytest.param('getattr(x, "columns")\n', "getattr(x, 'columns')", id="call"),
        pytest.param("hasattr(x, 'columns')\n", "hasattr(x, 'columns')", id="single-quoted"),
        pytest.param('getattr(x, "columns", None)\n', "getattr(x, 'columns', …)", id="default"),
        pytest.param('setattr(x, "columns", 1)\n', "setattr(x, 'columns', …)", id="value"),
        pytest.param('patch.object(x, "columns")\n', "patch.object(x, 'columns')", id="patch-object"),
        pytest.param('patch.object(x, "columns", autospec=True)\n', "patch.object(x, 'columns', …)", id="keyword"),
        pytest.param('mocker.patch.object(engine, "columns")\n', "mocker.patch.object(engine, 'columns')",
                     id="unresolved-callee"),
        pytest.param('monkeypatch.setattr(obj, "columns", 1)\n', "monkeypatch.setattr(obj, 'columns', …)",
                     id="unresolved-callee-with-value"),
        pytest.param('getattr(a.b[0], "columns")\n', "getattr(a.b[0], 'columns')", id="expression-object"),
        pytest.param('getattr(x, "columns",)\n', "getattr(x, 'columns')", id="trailing-comma"),
    ],
)
def test_a_call_site_prints_callee_object_and_member(text: str, site: str) -> None:
    assert _site(text, _argument, "columns") == site


@pytest.mark.parametrize(
    ("text", "obj", "site"),
    [
        pytest.param('R.model_fields["columns"]\n', _subscripted, "R.model_fields['columns']", id="subscript"),
        pytest.param('R.model_fields.get("columns")\n', _got, "R.model_fields.get('columns')", id="get"),
        pytest.param('"columns" in R.model_fields\n', _container, "'columns' in R.model_fields", id="in"),
        pytest.param('"columns" not in r.model_fields_set\n', _container, "'columns' not in r.model_fields_set",
                     id="not-in"),
        pytest.param('type(r).model_fields["columns"]\n', _subscripted, "type(r).model_fields['columns']",
                     id="expression-receiver"),
    ],
)
def test_a_field_name_read_prints_as_written(text: str, obj: Pick, site: str) -> None:
    assert _site(text, obj, "columns") == site


@pytest.mark.parametrize(
    ("text", "obj", "site"),
    [
        pytest.param('getattr(\n    make(\n        1\n    ),\n    "columns",\n)\n', _argument, "getattr(make( 1 ), 'columns')",
                     id="call"),
        pytest.param('getattr(\n    make(\n        1\n    ),\n    "columns",\n    None,\n)\n', _argument,
                     "getattr(make( 1 ), 'columns', …)", id="call-with-default"),
        pytest.param('"columns"   in   R.model_fields\n', _container, "'columns' in R.model_fields", id="in"),
    ],
)
def test_a_site_collapses_each_run_of_whitespace(text: str, obj: Pick, site: str) -> None:
    assert _site(text, obj, "columns") == site
