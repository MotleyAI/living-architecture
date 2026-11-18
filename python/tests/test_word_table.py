"""Word tables: the shared schema, loading through `dr-refactor`, and every invalid form with its section and index."""

from __future__ import annotations

from pathlib import Path

import pytest
from project_files import file_tree, write_project
from refactor_cli import run_raw

from living_architecture.cli.dr_refactor import dr_refactor
from living_architecture.contract import language, message, schema, validate

ROW = {"from": "model", "to": "dataset"}


def _valid(document: object) -> bool:
    return validate(schema("word-table"), document) == []


@pytest.mark.parametrize(
    "document",
    [
        {"words": [ROW]},
        {"words": [ROW, {"from": "v1", "to": "v2"}], "carve_outs": [], "entries": []},
        {"words": [ROW], "carve_outs": [{"words": ["model"], "annotated": ["BaseModel", "_Private", "$Scope", "Modèle"]}]},
        {"words": [ROW], "carve_outs": [{"words": ["model"], "paths": ["pkg/sql/**", "*.py"]}]},
        {"words": [ROW], "carve_outs": [{"words": ["model"], "symbols": [{"file": "pkg/a.py", "symbol": "f(model)"}]}]},
        {"words": [ROW], "entries": [{"file": "pkg/a.py", "symbol": "A.model", "new_name": "population"},
                                     {"module": "pkg/model.py", "new_name": "table"}]},
    ],
    ids=["words", "empty-sections", "annotated", "paths", "symbols", "entries"],
)
def test_word_table_schema_accepts(document: object) -> None:
    assert _valid(document)


@pytest.mark.parametrize(
    "document",
    [
        [ROW],
        {},
        {"words": []},
        {"words": [ROW], "phrases": []},
        {"words": [{"from": "Model", "to": "dataset"}]},
        {"words": [{"from": "model", "to": "data_set"}]},
        {"words": [{"from": "2d", "to": "flat"}]},
        {"words": [{"from": "model", "to": "data set"}]},
        {"words": [{"from": "modèle", "to": "dataset"}]},
        {"words": [{"from": "model"}]},
        {"words": [{"from": "model", "to": "dataset", "plural": "datasets"}]},
        {"words": [["model", "dataset"]]},
        {"words": [ROW], "carve_outs": [{"words": ["model"]}]},
        {"words": [ROW], "carve_outs": [{"words": ["model"], "paths": ["a/**"], "annotated": ["T"]}]},
        {"words": [ROW], "carve_outs": [{"words": ["model"], "paths": ["a/**"], "symbols": [{"file": "a.py", "symbol": "f"}]}]},
        {"words": [ROW], "carve_outs": [{"words": [], "paths": ["a/**"]}]},
        {"words": [ROW], "carve_outs": [{"paths": ["a/**"]}]},
        {"words": [ROW], "carve_outs": [{"words": ["model"], "paths": []}]},
        {"words": [ROW], "carve_outs": [{"words": ["model"], "annotated": []}]},
        {"words": [ROW], "carve_outs": [{"words": ["model"], "annotated": ["list[Model]"]}]},
        {"words": [ROW], "carve_outs": [{"words": ["model"], "annotated": ["schema.Model"]}]},
        {"words": [ROW], "carve_outs": [{"words": ["model"], "annotated": ["2d"]}]},
        {"words": [ROW], "carve_outs": [{"words": ["model"], "symbols": [{"file": "a.py"}]}]},
        {"words": [ROW], "carve_outs": [{"words": ["model"], "symbols": ["f(model)"]}]},
        {"words": [ROW], "carve_outs": [{"words": ["model"], "paths": ["a/**"], "phrase": "data model"}]},
        {"words": [ROW], "entries": [{"file": "a.py", "symbol": "f", "new_name": "g", "retarget": "h"}]},
        {"words": [ROW], "entries": [{"file": "a.py", "new_name": "g"}]},
        {"words": [ROW], "entries": [{"module": "a.py", "symbol": "f", "new_name": "g"}]},
        {"words": [ROW], "entries": ["f"]},
        {"words": [ROW], "carve_outs": [{"words": ["model"], "paths": [""]}]},
        {"words": [ROW], "carve_outs": [{"words": ["model"], "symbols": []}]},
        {"words": [ROW], "carve_outs": [{"words": ["model"], "symbols": [{"file": "", "symbol": "f"}]}]},
        {"words": [ROW], "carve_outs": [{"words": ["model"], "symbols": [{"file": "a.py", "symbol": ""}]}]},
        {"words": [ROW], "carve_outs": [{"words": ["model"], "symbols": [{"file": "a.py", "symbol": "f", "new_name": "g"}]}]},
    ],
    ids=["a-list", "no-words", "empty-words", "unknown-section", "uppercase-from", "underscore-to", "digit-first",
         "two-words", "non-ascii-word", "no-to", "unknown-row-key", "row-not-a-mapping", "no-matcher", "paths-and-annotated",
         "paths-and-symbols", "empty-carve-words", "no-carve-words", "empty-paths", "empty-annotated",
         "annotated-subscript", "annotated-dotted", "annotated-digit-first", "symbol-without-path",
         "symbol-not-a-mapping", "unknown-carve-key", "entry-both-intents", "entry-no-locator", "module-entry-with-symbol",
         "entry-not-a-mapping", "empty-path", "empty-symbols", "empty-symbol-file", "empty-symbol-path", "unknown-symbol-key"],
)
def test_word_table_schema_rejects(document: object) -> None:
    assert not _valid(document)


def test_fixture_decorators_come_from_the_language_registry() -> None:
    assert (language("python")["fixture_decorators"], language("typescript")["fixture_decorators"]) == (
        ["pytest.fixture", "pytest_asyncio.fixture"], [])


SOURCE = "model_name = 'm'\n\n\ndef f(model: str) -> str:\n    return model\n"
VALID = "words:\n- {from: model, to: dataset}\n"


def _invalid(*items: tuple[str, int], table: str = "words.yaml") -> str:
    return "".join(message("refactor.words-invalid", table=table, section=s, index=i) + "\n" for s, i in items)


def _generate(tmp_path: Path, table: str | None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
              *, source: str = SOURCE) -> tuple[int, str, str]:
    files = {"pkg/a.py": source, **({} if table is None else {"words.yaml": table})}
    root = write_project(tmp_path / "proj", files)
    return run_raw(root, ["generate-map", "words.yaml"], monkeypatch, capsys)


UNORDERED = """\
entries:
- {file: pkg/a.py}
carve_outs:
- {words: [model]}
- {words: [model], paths: ['a/**']}
- {words: [x], paths: ['a/**']}
words:
- {from: model, to: dataset}
- {from: A, to: b}
- {from: c, to: c}
"""
INVALID: dict[str, tuple[str, list[tuple[str, int]]]] = {
    "uppercase-from": ("words:\n- {from: model, to: dataset}\n- {from: Columns, to: fields}\n", [("words", 2)]),
    "from-equals-to": ("words:\n- {from: model, to: model}\n", [("words", 1)]),
    "from-given-twice": ("words:\n- {from: model, to: dataset}\n- {from: model, to: table}\n", [("words", 2)]),
    "row-without-to": ("words:\n- {from: model}\n", [("words", 1)]),
    "yaml-boolean-word": ("words:\n- {from: model, to: dataset}\n- {from: off, to: on}\n", [("words", 2)]),
    "empty-words": ("words: []\n", [("words", 1)]),
    "no-words": ("carve_outs: []\n", [("words", 1)]),
    "words-not-a-list": ("words: {model: dataset}\n", [("words", 1)]),
    "a-list": ("- {from: model, to: dataset}\n", [("words", 1)]),
    "not-yaml": ("words: [\n", [("words", 1)]),
    "two-matchers": (VALID + "carve_outs:\n- {words: [model], paths: ['a/**'], annotated: [T]}\n", [("carve_outs", 1)]),
    "no-matcher": (VALID + "carve_outs:\n- {words: [model], paths: ['a/**']}\n- {words: [model]}\n", [("carve_outs", 2)]),
    "word-that-is-no-from": (VALID + "carve_outs:\n- {words: [model, columns], paths: ['a/**']}\n", [("carve_outs", 1)]),
    "to-is-no-from": (VALID + "carve_outs:\n- {words: [dataset], paths: ['a/**']}\n", [("carve_outs", 1)]),
    "annotated-not-an-identifier": (VALID + "carve_outs:\n- {words: [model], annotated: ['list[Model]']}\n",
                                    [("carve_outs", 1)]),
    "entry-with-both-intents": (VALID + "entries:\n- {file: pkg/a.py, symbol: f, new_name: g, retarget: h}\n",
                                [("entries", 1)]),
    "entry-without-a-locator": (VALID + "entries:\n- {file: pkg/a.py, symbol: f, new_name: g}\n- {file: pkg/a.py, new_name: g}\n",
                                [("entries", 2)]),
    "sections-in-order": (
        UNORDERED,
        [("words", 2), ("words", 3), ("carve_outs", 1), ("carve_outs", 3), ("entries", 1)]),
}


@pytest.mark.parametrize(("table", "items"), INVALID.values(), ids=INVALID.keys())
def test_an_invalid_table_names_each_item_by_section_and_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    table: str, items: list[tuple[str, int]],
) -> None:
    assert _generate(tmp_path, table, monkeypatch, capsys) == (2, "", _invalid(*items))


def test_a_missing_table_names_words_item_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _generate(tmp_path, None, monkeypatch, capsys) == (2, "", _invalid(("words", 1)))


def test_a_valid_table_generates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    code, _out, err = _generate(tmp_path, VALID, monkeypatch, capsys)
    assert (code, err) == (0, "")


COMMANDS: dict[str, list[str]] = {
    "rename": ["rename", "--file", "pkg/a.py", "--symbol", "f", "--new-name", "g"],
    "rename-map": ["rename-map", "renames.yaml"],
    "retarget": ["retarget", "--file", "pkg/a.py", "--symbol", "alias", "--target", "f"],
}
ALIASED = SOURCE + "\n\nalias = f\n"
RENAMES = "- {file: pkg/a.py, symbol: f, new_name: g}\n"


@pytest.mark.parametrize("argv", COMMANDS.values(), ids=COMMANDS.keys())
def test_words_option_refuses_an_invalid_table_before_any_reference_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/a.py": ALIASED, "renames.yaml": RENAMES,
                                             "words.yaml": "words:\n- {from: Model, to: dataset}\n"})
    before = file_tree(root)
    code, out, err = run_raw(root, ["--apply", *argv, "--words", "words.yaml"], monkeypatch, capsys)
    assert (code, out, "[references]" in err, err.endswith(_invalid(("words", 1))), file_tree(root) == before) == (
        2, "", False, True, True)


def _unresolved_carve(symbol: str) -> str:
    return VALID + f"carve_outs:\n- words: [model]\n  symbols:\n  - {{file: pkg/a.py, symbol: '{symbol}'}}\n"


def test_a_carve_out_symbol_that_resolves_to_nothing_is_refused_by_generate_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _generate(tmp_path, _unresolved_carve("f(modle)"), monkeypatch, capsys)
    expected = message("refactor.symbol-unresolved", path="pkg/a.py", symbol="f(modle)", candidates="model")
    assert (code, out, err) == (2, "", expected + "\n")


@pytest.mark.parametrize("argv", COMMANDS.values(), ids=COMMANDS.keys())
def test_a_carve_out_symbol_that_resolves_to_nothing_is_refused_with_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/a.py": ALIASED, "renames.yaml": RENAMES,
                                             "words.yaml": _unresolved_carve("f(modle)")})
    code, out, err = run_raw(root, [*argv, "--words", "words.yaml"], monkeypatch, capsys)
    expected = message("refactor.symbol-unresolved", path="pkg/a.py", symbol="f(modle)", candidates="model")
    assert (code, out, "[references]" in err, err.endswith(expected + "\n")) == (2, "", False, True)


def test_a_table_is_read_relative_to_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/a.py": SOURCE, "tables/words.yaml": VALID})
    (root / "tools").mkdir()
    monkeypatch.chdir(root / "tools")
    code = dr_refactor(["--project", "..", "generate-map", "../tables/words.yaml"])
    out, err = capsys.readouterr()
    assert (code, out.splitlines()[0], err) == (0, "- {file: pkg/a.py, symbol: model_name, new_name: dataset_name}", "")
