"""Python `refactor.string_forms`: strings of a declared mini-language are respelled with a class or module-level symbol."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from refactor_cli import git_project, leftover, read, rename_argv, run

from living_architecture.config import ConfigError, load_config

FORMS = [r"NODE TABLE (\w+)", r"\(\w*:(\w+)\)"]
CONFIG = "refactor:\n  string_forms:\n" + "".join(f"  - '{form}'\n" for form in FORMS)
MODEL = 'class Model:\n    name: str = ""\n\n\n'
MODEL_AFTER = MODEL.replace("class Model", "class Dataset")
SCHEMA = 'SCHEMA = "CREATE NODE TABLE Model(name STRING, PRIMARY KEY(name))"\n'
FIND = 'FIND = "MATCH (m:Model) RETURN m.name"\n'


@pytest.fixture
def forms(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Rename `Model -> Dataset` (or `argv`) under the Cypher forms; returns the root and the run."""

    def go(files: dict[str, str], *flags: str, argv: list[str] | None = None, config: str = CONFIG):
        root = git_project(tmp_path / "proj", files, config)
        return root, run(root, argv or rename_argv("pkg/g.py", "Model", "Dataset", *flags), monkeypatch, capsys)

    return go


def _renamed(text: str) -> str:
    return text.replace("Model", "Dataset")


def test_labels_follow_the_class_without_docs(forms) -> None:
    root, (code, _out, err) = forms({"pkg/g.py": MODEL + SCHEMA + FIND})
    assert (code, err) == (0, "")
    assert read(root, "pkg/g.py") == MODEL_AFTER + _renamed(SCHEMA) + _renamed(FIND)


def test_a_form_in_another_file_follows_the_class(forms) -> None:
    root, (code, _out, err) = forms({"pkg/g.py": MODEL, "pkg/q.py": FIND})
    assert (code, err) == (0, "")
    assert read(root, "pkg/q.py") == _renamed(FIND)


def test_every_site_of_a_string_is_rewritten(forms) -> None:
    text = 'JOIN = "MATCH (a:Model)-[:HAS]->(b:Model)"\n'
    root, (code, _out, _err) = forms({"pkg/g.py": MODEL + text})
    assert code == 0
    assert read(root, "pkg/g.py") == MODEL_AFTER + _renamed(text)


def test_an_f_string_part_holds_form_sites(forms) -> None:
    text = 'def find(i: int) -> str:\n    return f"MATCH (m:Model) WHERE m.id = {i} RETURN (n:Model)"\n'
    root, (code, _out, _err) = forms({"pkg/g.py": MODEL + text})
    assert code == 0
    assert read(root, "pkg/g.py") == MODEL_AFTER + _renamed(text)


@pytest.mark.parametrize("docs", [False, True], ids=["plain", "docs"])
def test_another_symbol_in_the_form_and_a_plain_word_are_unchanged(forms, docs: bool) -> None:
    text = 'OTHER = "MATCH (m:ModelColumn)"\nPROSE = "a Model in prose"\n'
    root, (code, _out, err) = forms({"pkg/g.py": MODEL + text}, *(["--docs"] if docs else []))
    assert code == 0
    assert read(root, "pkg/g.py") == MODEL_AFTER + text
    assert err == (f"{leftover('pkg/g.py', 6, 'string', 'Model')}\n" if docs else "")


def test_a_rewritten_form_site_is_not_listed_as_a_docs_mention(forms) -> None:
    root, (code, _out, err) = forms({"pkg/g.py": MODEL + FIND}, "--docs")
    assert (code, err) == (0, "")
    assert read(root, "pkg/g.py") == MODEL_AFTER + _renamed(FIND)


@pytest.mark.parametrize("docs", [False, True], ids=["plain", "docs"])
@pytest.mark.parametrize(
    "other",
    [
        MODEL,
        "Model, rest = 1, 2\n",
        "[first, *Model] = [1, 2]\n",
        "first, (Model, rest) = 1, (2, 3)\n",
        "from json import JSONDecoder as Model\n",
        "import json as Model\n",
    ],
    ids=["class", "tuple", "starred", "nested", "from-import", "import"],
)
def test_a_simple_name_collision_lists_every_form_site(forms, docs: bool, other: str) -> None:
    files = {"pkg/g.py": MODEL + SCHEMA + FIND, "pkg/other.py": other}
    root, (code, _out, err) = forms(files, *(["--docs"] if docs else []))
    assert code == 0
    assert read(root, "pkg/g.py") == MODEL_AFTER + SCHEMA + FIND
    assert err.splitlines() == [leftover("pkg/g.py", 5, "string", "Model"), leftover("pkg/g.py", 6, "string", "Model")]


@pytest.mark.parametrize("docs", [False, True], ids=["plain", "docs"])
def test_an_import_of_the_renamed_class_is_no_collision(forms, docs: bool) -> None:
    files = {"pkg/g.py": MODEL, "pkg/other.py": "from pkg.g import Model\n\n" + FIND + "\nprint(Model)\n"}
    root, (code, _out, err) = forms(files, *(["--docs"] if docs else []))
    assert (code, err) == (0, "")
    assert read(root, "pkg/other.py") == "from pkg.g import Dataset\n\n" + _renamed(FIND) + "\nprint(Dataset)\n"


def test_a_collision_renamed_to_the_same_name_by_the_run_rewrites_the_sites(forms) -> None:
    entries = [{"file": "pkg/g.py", "symbol": "Model", "new_name": "Dataset"},
               {"file": "pkg/other.py", "symbol": "Model", "new_name": "Dataset"}]
    files = {"pkg/g.py": MODEL + FIND, "pkg/other.py": MODEL, "map.yaml": yaml.safe_dump(entries, sort_keys=False)}
    root, (code, _out, err) = forms(files, argv=["--apply", "rename-map", "map.yaml"])
    assert (code, err) == (0, "")
    assert read(root, "pkg/g.py") == MODEL_AFTER + _renamed(FIND)


def test_a_pick_rewrites_a_listed_form_site(forms) -> None:
    files = {"pkg/g.py": MODEL + SCHEMA + FIND, "pkg/other.py": MODEL}
    root, (code, _out, err) = forms(files, "--docs", "--docs-pick", "pkg/g.py:5")
    assert code == 0
    assert read(root, "pkg/g.py") == MODEL_AFTER + _renamed(SCHEMA) + FIND
    assert err == f"{leftover('pkg/g.py', 6, 'string', 'Model')}\n"


def test_a_kept_line_keeps_its_form_site(forms) -> None:
    root, (code, _out, err) = forms({"pkg/g.py": MODEL + SCHEMA + FIND}, "--keep", "pkg/g.py:5")
    assert (code, err) == (0, "")
    assert read(root, "pkg/g.py") == MODEL_AFTER + SCHEMA + _renamed(FIND)


def test_a_kept_literal_keeps_its_form_site(forms) -> None:
    text = 'QUERIES = {"version": 1, "find": "MATCH (m:Model)"}\n'
    root, (code, _out, err) = forms({"pkg/g.py": MODEL + text + FIND}, "--keep-literal", "version")
    assert (code, err) == (0, "")
    assert read(root, "pkg/g.py") == MODEL_AFTER + text + _renamed(FIND)


@pytest.mark.parametrize(
    "text",
    ['ESCAPED = "MATCH (m:\\x4dodel)"\n', 'ACCENT = "MATCH (m:Model) // mod\u00e8le"\n'],
    ids=["escape", "non-ascii"],
)
def test_the_raw_source_text_is_matched(forms, text: str) -> None:
    root, (code, _out, err) = forms({"pkg/g.py": MODEL + text})
    assert (code, err) == (0, "")
    assert read(root, "pkg/g.py") == MODEL_AFTER + text


def test_a_non_ascii_literal_is_a_docs_mention_only(forms) -> None:
    text = 'ACCENT = "MATCH (m:Model) // mod\u00e8le"\n'
    root, (code, _out, err) = forms({"pkg/g.py": MODEL + text}, "--docs")
    assert code == 0
    assert read(root, "pkg/g.py") == MODEL_AFTER + text
    assert err == f"{leftover('pkg/g.py', 5, 'string', 'Model')}\n"


def test_a_non_ascii_f_string_part_does_not_hide_an_ascii_one(forms) -> None:
    text = 'def find(i: int) -> str:\n    return f"MATCH (m:Model) {i} // mod\u00e8le (n:Model)"\n'
    root, (code, _out, _err) = forms({"pkg/g.py": MODEL + text})
    assert code == 0
    assert read(root, "pkg/g.py") == MODEL_AFTER + text.replace('f"MATCH (m:Model)', 'f"MATCH (m:Dataset)')


def test_a_module_level_function_uses_the_forms(forms) -> None:
    text = 'def lookup() -> int:\n    return 1\n\n\nCALL = "RETURN (x:lookup)"\n'
    root, (code, _out, err) = forms({"pkg/g.py": text}, argv=rename_argv("pkg/g.py", "lookup", "search"))
    assert (code, err) == (0, "")
    assert read(root, "pkg/g.py") == text.replace("lookup", "search")


@pytest.mark.parametrize(
    ("symbol", "text"),
    [
        ("Model.name", MODEL + 'FIND = "MATCH (m:name)"\n'),
        ("find(name)", 'def find(name: str) -> str:\n    return name + "MATCH (m:name)"\n'),
        ("find.<locals>.name", 'def find() -> str:\n    name = "x"\n    return name + "MATCH (m:name)"\n'),
    ],
    ids=["member", "parameter", "local"],
)
def test_other_renames_ignore_the_forms(forms, symbol: str, text: str) -> None:
    root, (code, _out, err) = forms({"pkg/g.py": text}, argv=rename_argv("pkg/g.py", symbol, "title"))
    assert (code, err) == (0, "")
    assert '"MATCH (m:name)"' in read(root, "pkg/g.py")
    assert "title" in read(root, "pkg/g.py")


def test_a_module_rename_ignores_the_forms(forms) -> None:
    use = 'from pkg.model import MODEL\n\nFIND = "MATCH (m:model)"\n'
    argv = ["--apply", "rename", "--file", "pkg/model.py", "--new-name", "dataset"]
    root, (code, _out, err) = forms({"pkg/model.py": "MODEL = 1\n", "pkg/g.py": use}, argv=argv)
    assert (code, err) == (0, "")
    assert read(root, "pkg/g.py") == use.replace("pkg.model", "pkg.dataset")


def test_without_forms_the_strings_are_unchanged(forms) -> None:
    root, (code, _out, err) = forms({"pkg/g.py": MODEL + FIND}, config="")
    assert (code, err) == (0, "")
    assert read(root, "pkg/g.py") == MODEL_AFTER + FIND


def _write(root: Path, patterns: list[str]) -> None:
    (root / "living-architecture.yaml").write_text(yaml.safe_dump({"refactor": {"string_forms": patterns}}), encoding="utf-8")


def test_string_forms_are_read_from_the_refactor_section(tmp_path: Path) -> None:
    _write(tmp_path, FORMS)
    assert list(load_config(tmp_path).refactor.string_forms) == FORMS
    assert list(load_config(tmp_path / "missing").refactor.string_forms) == []


INVALID = {
    "no-group": r"NODE TABLE \w+",
    "non-capturing-only": r"NODE TABLE (?:\w+)",
    "two-groups": r"(\w+) TABLE (\w+)",
    "named-group": r"NODE TABLE (?P<name>\w+)",
    "lookahead": r"NODE TABLE (\w+)(?=\()",
    "does-not-compile": r"NODE TABLE (\w+",
}


@pytest.mark.parametrize("pattern", INVALID.values(), ids=INVALID.keys())
def test_an_invalid_form_is_a_configuration_error_naming_the_key_and_the_pattern(tmp_path: Path, pattern: str) -> None:
    _write(tmp_path, [FORMS[0], pattern])
    with pytest.raises(ConfigError) as caught:
        load_config(tmp_path)
    assert "refactor.string_forms" in str(caught.value)
    assert pattern in str(caught.value)


@pytest.mark.parametrize("value", ["NODE (\\w+)", [3], [None]], ids=["not-a-list", "number", "null"])
def test_string_forms_must_be_a_list_of_strings(tmp_path: Path, value: object) -> None:
    (tmp_path / "living-architecture.yaml").write_text(yaml.safe_dump({"refactor": {"string_forms": value}}), encoding="utf-8")
    with pytest.raises(ConfigError, match="string_forms"):
        load_config(tmp_path)


def test_a_group_inside_a_non_capturing_group_counts_once(tmp_path: Path) -> None:
    pattern = r"(?:NODE|REL) TABLE (\w+)"
    _write(tmp_path, [pattern])
    assert list(load_config(tmp_path).refactor.string_forms) == [pattern]


def test_an_escaped_parenthesis_is_not_a_group(tmp_path: Path) -> None:
    _write(tmp_path, [FORMS[1], r"[(](\w+)[)]"])
    assert len(load_config(tmp_path).refactor.string_forms) == 2


def test_dr_refactor_exits_2_on_an_invalid_form(forms) -> None:
    root, (code, out, err) = forms({"pkg/g.py": MODEL + FIND}, config="refactor:\n  string_forms: ['(a)(b)']\n")
    assert (code, out) == (2, "")
    assert "refactor.string_forms" in err
    assert "(a)(b)" in err
    assert read(root, "pkg/g.py") == MODEL + FIND
