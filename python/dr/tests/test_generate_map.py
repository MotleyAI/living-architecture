"""Python `dr-refactor generate-map`: candidates, carve-outs, entries, locals and the map it prints."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from deterministic_refactor.contract import message, schema, validate
from deterministic_refactor.refactor.occurrence_index import ServerSession
from project_files import file_tree, write_project
from refactor_cli import read, run, run_raw

MODEL = "words:\n- {from: model, to: dataset}\n"
COLUMNS = "words:\n- {from: columns, to: fields}\n"
ANNOTATED = COLUMNS + "carve_outs:\n- {words: [columns], annotated: [IntrospectedColumn]}\n"

Generated = tuple[int, str, str]


def _generate(
    tmp_path: Path, files: dict[str, str], table: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    *flags: str,
) -> Generated:
    root = write_project(tmp_path / "proj", {**files, "words.yaml": table})
    return run_raw(root, [*flags, "generate-map", "words.yaml"], monkeypatch, capsys)


def _entry(file: str, symbol: str, new_name: str) -> str:
    return f"- {{file: {file}, symbol: {symbol}, new_name: {new_name}}}\n"


def _carved(path: str, line: int, name: str, word: str, matcher: str) -> str:
    return message("refactor.carved", path=path, line=line, name=name, word=word, matcher=matcher) + "\n"


PARAMETER = """\
columns_total = 0


def f(columns{annotation}) -> None:
    print(columns)
"""
ANNOTATIONS: dict[str, tuple[str, bool]] = {
    "subscript": (": list[IntrospectedColumn]", True),
    "string-union": (': "IntrospectedColumn | None"', True),
    "dotted": (": schema.IntrospectedColumn", True),
    "union": (": IntrospectedColumn | None", True),
    "string-inside-a-subscript": (': dict[str, list["IntrospectedColumn"]]', True),
    "another-type": (": list[str]", False),
    "none": ("", False),
    "longer-identifier": (": IntrospectedColumns", False),
    "longer-identifier-in-a-string": (': "XIntrospectedColumn"', False),
    "another-case": (": list[introspectedcolumn]", False),
    "default-value-only": (": object = IntrospectedColumn", False),
}


@pytest.mark.parametrize(("annotation", "carved"), ANNOTATIONS.values(), ids=ANNOTATIONS.keys())
def test_annotated_matches_identifier_tokens_of_the_written_annotation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], annotation: str, carved: bool
) -> None:
    files = {"pkg/c.py": PARAMETER.format(annotation=annotation)}
    total = _entry("pkg/c.py", "columns_total", "fields_total")
    expected = (
        (0, total, _carved("pkg/c.py", 4, "columns", "columns", "annotated IntrospectedColumn"))
        if carved
        else (0, total + _entry("pkg/c.py", "f(columns)", "fields"), "")
    )
    assert _generate(tmp_path, files, ANNOTATED, monkeypatch, capsys) == expected


KINDS = """\
columns: list[IntrospectedColumn] = []


class Ds:
    columns: list[IntrospectedColumn] = []

    def __init__(self) -> None:
        self.all_columns: list[IntrospectedColumn] = []


def f() -> None:
    columns: list[IntrospectedColumn] = []
    print(columns)


def get_columns() -> list[IntrospectedColumn]:
    return []
"""


def test_annotated_matches_variables_fields_attributes_and_locals_but_no_function(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    listed = "".join(
        _carved("pkg/c.py", line, name, "columns", "annotated IntrospectedColumn")
        for line, name in ((1, "columns"), (5, "columns"), (8, "all_columns"), (12, "columns"))
    )
    assert _generate(tmp_path, {"pkg/c.py": KINDS}, ANNOTATED, monkeypatch, capsys) == (
        0, _entry("pkg/c.py", "get_columns", "get_fields"), listed)


def test_the_first_matching_carve_out_in_table_order_is_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    table = COLUMNS + "carve_outs:\n- {words: [columns], paths: ['pkg/*.py']}\n- {words: [columns], annotated: [IntrospectedColumn]}\n"
    files = {"pkg/c.py": PARAMETER.format(annotation=": list[IntrospectedColumn]"), "tests/t.py": "columns = 1\n"}
    listed = _carved("pkg/c.py", 1, "columns_total", "columns", "paths pkg/*.py") + _carved(
        "pkg/c.py", 4, "columns", "columns", "paths pkg/*.py")
    assert _generate(tmp_path, files, table, monkeypatch, capsys) == (0, _entry("tests/t.py", "columns", "fields"), listed)


CANDIDATES = """\
import json as model_codec
from pkg.other import Model
from pkg.other import Model as BaseModel


class ModelStore(BaseModel):
    model_count: int = 0

    def __init__(self) -> None:
        self.model = Model()

    def get_model(self, model_name: str) -> str:
        return model_codec.dumps(model_name)


def load(model: str) -> str:
    def inner_model() -> str:
        return model

    return inner_model()
"""
OTHER = "class Model:\n    pass\n"


def test_candidates_are_written_by_path_in_source_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    expected = "".join(
        _entry("pkg/a.py", symbol, new)
        for symbol, new in (
            ("model_codec", "dataset_codec"),
            ("BaseModel", "BaseDataset"),
            ("ModelStore", "DatasetStore"),
            ("ModelStore.model_count", "dataset_count"),
            ("ModelStore.model", "dataset"),
            ("ModelStore.get_model", "get_dataset"),
            ("ModelStore.get_model(model_name)", "dataset_name"),
            ("load(model)", "dataset"),
            ("load.<locals>.inner_model", "inner_dataset"),
        )
    ) + _entry("pkg/other.py", "Model", "Dataset")
    files = {"pkg/a.py": CANDIDATES, "pkg/other.py": OTHER}
    assert _generate(tmp_path, files, MODEL, monkeypatch, capsys) == (0, expected, "")


ONE_SYMBOL = """\
class Model:
    pass


class Model:
    pass


class Store:
    @property
    def model(self) -> int:
        return 1

    @model.setter
    def model(self, value: int) -> None:
        print(value)
"""


def test_declarations_of_one_symbol_are_one_candidate_at_the_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    expected = _entry("pkg/a.py", "Model", "Dataset") + _entry("pkg/a.py", "Store.model", "dataset")
    assert _generate(tmp_path, {"pkg/a.py": ONE_SYMBOL}, MODEL, monkeypatch, capsys) == (0, expected, "")


COMPREHENSION = "def f(items: list[str]) -> list[str]:\n    return [model for model in items]\n"


def test_a_declaration_no_path_reaches_is_written_by_line_and_column(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    expected = "- {file: pkg/a.py, line: 2, col: 23, new_name: dataset}\n"
    assert _generate(tmp_path, {"pkg/a.py": COMPREHENSION}, MODEL, monkeypatch, capsys) == (0, expected, "")


LAMBDA = "model_name = 'm'\n\n\ndef pick(items: list[str]) -> list[str]:\n    return sorted(items, key=lambda model: model)\n"


def test_a_lambda_parameter_is_listed_and_not_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    listed = message("refactor.not-generated", path="pkg/a.py", line=5, name="model", word="model") + "\n"
    assert _generate(tmp_path, {"pkg/a.py": LAMBDA}, MODEL, monkeypatch, capsys) == (
        0, _entry("pkg/a.py", "model_name", "dataset_name"), listed)


def test_no_language_server_is_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def started(_session: ServerSession) -> None:
        raise AssertionError("a language server was started")

    monkeypatch.setattr(ServerSession, "get", started)
    assert _generate(tmp_path, {"pkg/a.py": LAMBDA}, MODEL, monkeypatch, capsys)[:2] == (
        0, _entry("pkg/a.py", "model_name", "dataset_name"))


MODULES = {
    "model_tools.py": "X = 1\n",
    "pkg/model.py": "X = 1\n",
    "pkg/model_io/__init__.py": "",
    "pkg/model_io/reader.py": "X = 1\n",
    "pkg/model_ns/part.py": "X = 1\n",
    ".venv/lib/model.py": "model = 1\n",
}
MODULE_ENTRIES = (
    "- {module: model_tools.py, new_name: dataset_tools}\n"
    "- {module: pkg/model.py, new_name: dataset}\n"
    "- {module: pkg/model_io/__init__.py, new_name: dataset_io}\n"
)


def test_module_files_and_packages_are_module_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _generate(tmp_path, MODULES, MODEL, monkeypatch, capsys) == (0, MODULE_ENTRIES, "")


def test_only_a_paths_carve_out_keeps_a_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    table = MODEL + "carve_outs:\n- {words: [model], annotated: [X]}\n- {words: [model], paths: ['pkg/model.py']}\n"
    code, out, _err = _generate(tmp_path, MODULES, table, monkeypatch, capsys)
    # The listing of a carved module is not pinned here: its template takes a line a module does not have.
    assert (code, out) == (0, MODULE_ENTRIES.replace("- {module: pkg/model.py, new_name: dataset}\n", ""))


LOCALS = """\
def f(name: str) -> str:
    model = name.upper()
    return model


def g(name: str) -> str:
    model = name.lower()
    return model


def h(name: str, model: str) -> str:
    models = name + model
    return models
"""


def test_same_named_locals_are_one_wildcard_and_a_parameter_is_its_own_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    expected = _entry("pkg/l.py", "'*.<locals>.model'", "dataset") + _entry("pkg/l.py", "h(model)", "dataset")
    assert _generate(tmp_path, {"pkg/l.py": LOCALS}, MODEL, monkeypatch, capsys) == (0, expected, "")


THREE = LOCALS + "\n\ndef k(name: str) -> str:\n    model = name.title()\n    return model\n"


def test_a_local_located_by_an_entry_leaves_the_others_each_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    table = MODEL + "entries:\n- {file: pkg/l.py, symbol: g.<locals>.model, new_name: population}\n"
    expected = (
        _entry("pkg/l.py", "g.<locals>.model", "population")
        + _entry("pkg/l.py", "f.<locals>.model", "dataset")
        + _entry("pkg/l.py", "h(model)", "dataset")
        + _entry("pkg/l.py", "k.<locals>.model", "dataset")
    )
    assert _generate(tmp_path, {"pkg/l.py": THREE}, table, monkeypatch, capsys) == (0, expected, "")


def test_locals_of_two_files_are_never_one_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    one = "def f() -> str:\n    model = 'x'\n    return model\n"
    expected = _entry("pkg/a.py", "f.<locals>.model", "dataset") + _entry("pkg/b.py", "f.<locals>.model", "dataset")
    assert _generate(tmp_path, {"pkg/a.py": one, "pkg/b.py": one}, MODEL, monkeypatch, capsys) == (0, expected, "")


KIND = """\
from typing import Literal

Kind = Literal['fast', 'slow']
LIMIT = 3


def load() -> int:
    return 1


def save() -> int:
    return 2


alias = load
"""
ODD_ENTRIES = """\
entries:
- {new_name: 'yes', symbol: load, file: pkg/a.py}
- {file: pkg/a.py, symbol: "Kind['fast']", new_name: '123'}
- {col: 5, line: 11, file: pkg/a.py, new_name: store}
- {file: pkg/a.py, offset: 59, new_name: CAP}
- {retarget: load, symbol: alias, file: pkg/a.py}
"""
# A value is written plain unless YAML would read it as something else or it holds a character outside
# `A-Za-z0-9_$./<>()-`; then it is single-quoted, a quote doubled.
ODD_OUTPUT = """\
- {file: pkg/a.py, symbol: load, new_name: 'yes'}
- {file: pkg/a.py, symbol: 'Kind[''fast'']', new_name: '123'}
- {file: pkg/a.py, line: 11, col: 5, new_name: store}
- {file: pkg/a.py, offset: 59, new_name: CAP}
- {file: pkg/a.py, symbol: alias, retarget: load}
"""


def test_entries_are_written_first_in_table_order_with_keys_in_schema_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"pkg/a.py": KIND, "pkg/b.py": "model = 1\n"}
    assert _generate(tmp_path, files, MODEL + ODD_ENTRIES, monkeypatch, capsys) == (
        0, ODD_OUTPUT + _entry("pkg/b.py", "model", "dataset"), "")


def test_an_entry_that_does_not_resolve_is_refused_with_its_locators_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    table = MODEL + "entries:\n- {file: pkg/a.py, symbol: laod, new_name: read}\n"
    expected = message("refactor.symbol-unresolved", path="pkg/a.py", symbol="laod", candidates="Kind, LIMIT, Literal, alias, load, save")
    assert _generate(tmp_path, {"pkg/a.py": KIND, "pkg/b.py": "model = 1\n"}, table, monkeypatch, capsys) == (
        2, "", expected + "\n")


V = """\
class Query:
    measures: list[str] = []


def add_measures(q: Query, measures: list[str]) -> None:
    q.measures += measures


def census_sql(columns: list[str]) -> str:
    return ", ".join(columns)
"""
H = """\
class Base:
    def measures(self) -> int:
        return 1


class Sub(Base):
    def measures(self) -> int:
        return 2


def total(b: Base) -> int:
    return b.measures()
"""
MEASURES = "words:\n- {from: measures, to: metrics}\n"


def test_the_printed_map_is_a_valid_rename_map_one_flow_mapping_per_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _code, out, _err = _generate(tmp_path, {"pkg/a.py": CANDIDATES, "pkg/other.py": OTHER, "pkg/l.py": LOCALS}, MODEL,
                                 monkeypatch, capsys)
    lines = out.splitlines()
    assert (len(lines), [line for line in lines if not re.fullmatch(r"- \{.+\}", line)],
            validate(schema("rename-map"), yaml.safe_load(out))) == (12, [], [])


def test_the_output_is_the_same_on_every_run_and_nothing_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"pkg/a.py": CANDIDATES, "pkg/other.py": OTHER, "pkg/l.py": LOCALS}
    first = _generate(tmp_path, files, MODEL, monkeypatch, capsys, "--apply")
    before = file_tree(tmp_path / "proj")
    second = run_raw(tmp_path / "proj", ["generate-map", "words.yaml"], monkeypatch, capsys)
    assert (first == second, first[0], file_tree(tmp_path / "proj") == before) == (True, 0, True)


@pytest.mark.parametrize(
    ("source", "renamed"),
    [
        (V, ["class Query:\n    metrics: list[str] = []", "def add_metrics(q: Query, metrics: list[str]) -> None:\n    q.metrics += metrics"]),
        (H, ["class Base:\n    def metrics(self)", "class Sub(Base):\n    def metrics(self)", "return b.metrics()"]),
    ],
    ids=["field-function-parameter", "member-and-override"],
)
def test_rename_map_applies_the_generated_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], source: str, renamed: list[str]
) -> None:
    _code, out, _err = _generate(tmp_path, {"pkg/v.py": source}, MEASURES, monkeypatch, capsys)
    root = tmp_path / "proj"
    (root / "map.yaml").write_text(out, encoding="utf-8")
    code, _out, err = run(root, ["--apply", "rename-map", "map.yaml"], monkeypatch, capsys)
    text = read(root, "pkg/v.py")
    assert (code, err, [part for part in renamed if part not in text]) == (0, "", [])


def test_no_candidate_and_no_entry_is_generate_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    expected = message("refactor.generate-empty", table="words.yaml") + "\n"
    assert _generate(tmp_path, {"pkg/a.py": KIND}, MODEL, monkeypatch, capsys) == (1, "", expected)


def test_a_map_emptied_by_carve_outs_ends_with_generate_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    table = MODEL + "carve_outs:\n- {words: [model], paths: ['pkg/**']}\n"
    expected = _carved("pkg/b.py", 1, "model", "model", "paths pkg/**") + message(
        "refactor.generate-empty", table="words.yaml") + "\n"
    assert _generate(tmp_path, {"pkg/b.py": "model = 1\n"}, table, monkeypatch, capsys) == (1, "", expected)


def test_typescript_sources_of_a_python_project_need_a_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"pkg/b.py": "model = 1\n", "web/b.ts": "export const model = 1;\n"}
    expected = message("refactor.generate-language", languages="python, typescript") + "\n"
    assert _generate(tmp_path, files, MODEL, monkeypatch, capsys) == (2, "", expected)


def test_language_python_generates_the_python_map_of_a_mixed_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/b.py": "model = 1\n", "web/b.ts": "export const model = 1;\n",
                                             "words.yaml": MODEL})
    assert run_raw(root, ["generate-map", "words.yaml", "--language", "python"], monkeypatch, capsys) == (
        0, _entry("pkg/b.py", "model", "dataset"), "")
