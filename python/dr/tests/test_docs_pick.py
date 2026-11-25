"""Python `--docs-pick PATH:LINE[=ENTRY]`: the listed mentions of a line are rewritten; a pick that cannot apply refuses."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from project_files import file_tree
from refactor_cli import git_project, leftover, read, rename_argv, run
from trmv.contract import message

Run = tuple[int, str, str]

TABLES = (
    '"""Every table lists its ``columns``."""\n\n\n'
    'class Table:\n    """A table and its ``columns``."""\n\n    columns: list[str] = []\n\n\n'
    'class Result:\n    """A result and its ``columns``."""\n\n    columns: list[str] = []\n\n\n'
    "# Both keep their ``columns`` in order.\n"
)
TABLE_ENTRIES = [
    {"file": "pkg/a.py", "symbol": "Table.columns", "new_name": "fields"},
    {"file": "pkg/a.py", "symbol": "Result.columns", "new_name": "result_columns"},
]
XY = "class A:\n    x: int = 0\n\n\nclass B:\n    y: int = 0\n\n\n# x and y move together; x first\n# x before y\n"
XY_ENTRIES = [
    {"file": "pkg/m.py", "symbol": "A.x", "new_name": "p"},
    {"file": "pkg/m.py", "symbol": "B.y", "new_name": "q"},
]
DS = "from pydantic import BaseModel\n\n\nclass Ds(BaseModel):\n    columns: list[str] = []\n"
BODY = (
    "from typing import Any\n\n\n"
    "def post(path: str, json: dict[str, Any]) -> None: ...\n\n\n"
    "def rest_body() -> None:\n"
    '    post("/datasets", json={"name": "orders", "columns": ["id"]})\n'
)
API_MD = "# API\n\nSend columns, then read columns back.\nOld clients send columns too.\n"


@pytest.fixture
def picked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Run `argv` over `files` (a map's entries go to `map.yaml`); returns the root, the tree before and the run."""

    def go(files: dict[str, str], argv: list[str], entries: list[dict[str, str]] | None = None):
        extra = {} if entries is None else {"map.yaml": yaml.safe_dump(entries, sort_keys=False)}
        root = git_project(tmp_path / "proj", {**files, **extra})
        before = file_tree(root)
        return root, before, run(root, argv, monkeypatch, capsys)

    return go


def _map(*flags: str) -> list[str]:
    return ["--apply", "rename-map", "map.yaml", *flags]


def _ds(*flags: str) -> list[str]:
    return rename_argv("pkg/m.py", "Ds.columns", "fields", *flags)


def _unmatched(site: str) -> str:
    return message("refactor.pick-unmatched", site=site)


def _ambiguous(site: str, old: str = "columns") -> str:
    return message("refactor.pick-ambiguous", site=site, first=1, second=2, old=old)


def test_a_pick_with_an_entry_resolves_a_mention_two_entries_reach(picked) -> None:
    root, _before, (code, _out, err) = picked({"pkg/a.py": TABLES}, _map("--docs", "--docs-pick", "pkg/a.py:1=1"), TABLE_ENTRIES)
    assert code == 0
    assert read(root, "pkg/a.py").splitlines()[0] == '"""Every table lists its ``fields``."""'
    assert err == f"{leftover('pkg/a.py', 16, 'comment', 'columns')}\n"


def test_the_second_entry_can_be_picked(picked) -> None:
    root, _before, (code, _out, _err) = picked({"pkg/a.py": TABLES}, _map("--docs", "--docs-pick", "pkg/a.py:16=2"), TABLE_ENTRIES)
    assert code == 0
    assert read(root, "pkg/a.py").splitlines()[15] == "# Both keep their ``result_columns`` in order."


def test_a_bare_word_in_an_untyped_body_is_picked(picked) -> None:
    root, _before, (code, _out, err) = picked({"pkg/m.py": DS, "pkg/n.py": BODY}, _ds("--docs", "--docs-pick", "pkg/n.py:8"))
    assert (code, err) == (0, "")
    assert read(root, "pkg/n.py") == BODY.replace('"columns"', '"fields"')


def test_a_rename_is_entry_one(picked) -> None:
    root, _before, (code, _out, err) = picked({"pkg/m.py": DS, "pkg/n.py": BODY}, _ds("--docs", "--docs-pick", "pkg/n.py:8=1"))
    assert (code, err) == (0, "")
    assert read(root, "pkg/n.py") == BODY.replace('"columns"', '"fields"')


def test_a_prose_line_is_picked_with_every_mention_on_it(picked) -> None:
    files = {"pkg/m.py": DS, "docs/api.md": API_MD}
    root, _before, (code, _out, err) = picked(files, _ds("--docs", "--docs-pick", "docs/api.md:3"))
    assert code == 0
    assert read(root, "docs/api.md") == API_MD.replace("Send columns, then read columns", "Send fields, then read fields")
    assert err == f"{leftover('docs/api.md', 4, 'prose', 'columns')}\n"


def test_a_pick_without_an_entry_rewrites_each_old_name_to_its_own_new_name(picked) -> None:
    root, _before, (code, _out, err) = picked({"pkg/m.py": XY}, _map("--docs", "--docs-pick", "pkg/m.py:9"), XY_ENTRIES)
    assert code == 0
    assert read(root, "pkg/m.py").splitlines()[8:] == ["# p and q move together; p first", "# x before y"]
    assert err.splitlines() == [leftover("pkg/m.py", 10, "comment", "x"), leftover("pkg/m.py", 10, "comment", "y")]


def test_a_pick_with_an_entry_leaves_the_other_old_name_listed(picked) -> None:
    root, _before, (code, _out, err) = picked({"pkg/m.py": XY}, _map("--docs", "--docs-pick", "pkg/m.py:10=1"), XY_ENTRIES)
    assert code == 0
    assert read(root, "pkg/m.py").splitlines()[9] == "# p before y"
    assert leftover("pkg/m.py", 10, "comment", "y") in err.splitlines()
    assert leftover("pkg/m.py", 10, "comment", "x") not in err.splitlines()


def test_a_dry_run_shows_the_picked_edit_and_writes_nothing(picked) -> None:
    argv = ["rename-map", "map.yaml", "--docs", "--docs-pick", "pkg/a.py:1=1"]
    root, before, (code, out, _err) = picked({"pkg/a.py": TABLES}, argv, TABLE_ENTRIES)
    assert code == 0
    assert '+"""Every table lists its ``fields``."""' in out
    assert file_tree(root) == before


def test_a_pick_without_docs_is_refused_in_checks(picked, capsys: pytest.CaptureFixture[str]) -> None:
    root, before, (code, out, err) = picked({"pkg/a.py": TABLES}, _map("--docs-pick", "pkg/a.py:1=1"), TABLE_ENTRIES)
    assert (code, out, err) == (2, "", f"{message('refactor.pick-needs-docs')}\n")
    assert file_tree(root) == before


@pytest.mark.parametrize("site", ["pkg/gone.py:1", "pkg/a.py:99", "pkg/a.py:99=1"], ids=["no-file", "past-the-end", "with-entry"])
def test_a_pick_naming_no_file_or_line_is_refused(picked, site: str) -> None:
    root, before, (code, out, err) = picked({"pkg/a.py": TABLES}, _map("--docs", "--docs-pick", site), TABLE_ENTRIES)
    assert (code, out) == (2, "")
    assert err == f"{message('refactor.site-missing', option='--docs-pick', site=site)}\n"
    assert file_tree(root) == before


@pytest.mark.parametrize(
    "site",
    ["pkg/a.py:2", "pkg/a.py:5", "pkg/a.py:7", "pkg/a.py:1=3", "pkg/a.py:1=0"],
    ids=["no-mention", "rewritten-by-its-class", "code-edit", "entry-past-the-map", "entry-zero"],
)
def test_a_pick_matching_no_listed_mention_is_refused(picked, site: str) -> None:
    root, before, (code, out, err) = picked({"pkg/a.py": TABLES}, _map("--docs", "--docs-pick", site), TABLE_ENTRIES)
    assert (code, out, err) == (2, "", f"{_unmatched(site)}\n")
    assert file_tree(root) == before


def test_a_pick_for_an_entry_whose_old_name_the_line_lacks_is_refused(picked) -> None:
    text = XY + "# only x here\n"
    root, before, (code, _out, err) = picked({"pkg/m.py": text}, _map("--docs", "--docs-pick", "pkg/m.py:11=2"), XY_ENTRIES)
    assert (code, err) == (2, f"{_unmatched('pkg/m.py:11=2')}\n")
    assert file_tree(root) == before


def test_a_pick_without_an_entry_where_two_entries_differ_is_refused(picked) -> None:
    root, before, (code, out, err) = picked({"pkg/a.py": TABLES}, _map("--docs", "--docs-pick", "pkg/a.py:1"), TABLE_ENTRIES)
    assert (code, out, err) == (2, "", f"{_ambiguous('pkg/a.py:1')}\n")
    assert file_tree(root) == before


def test_two_picks_choosing_different_entries_refuse_naming_the_later(picked) -> None:
    argv = _map("--docs", "--docs-pick", "pkg/a.py:1=1", "--docs-pick", "pkg/a.py:1=2")
    root, before, (code, _out, err) = picked({"pkg/a.py": TABLES}, argv, TABLE_ENTRIES)
    assert (code, err) == (2, f"{_ambiguous('pkg/a.py:1=2')}\n")
    assert file_tree(root) == before


def test_two_picks_choosing_one_entry_agree(picked) -> None:
    argv = _map("--docs", "--docs-pick", "pkg/a.py:1=1", "--docs-pick", "pkg/a.py:1=1")
    root, _before, (code, _out, _err) = picked({"pkg/a.py": TABLES}, argv, TABLE_ENTRIES)
    assert code == 0
    assert read(root, "pkg/a.py").splitlines()[0] == '"""Every table lists its ``fields``."""'


def test_every_refused_pick_is_reported_in_pick_order(picked) -> None:
    argv = _map("--docs", "--docs-pick", "pkg/a.py:16", "--docs-pick", "pkg/a.py:2", "--docs-pick", "pkg/a.py:1=1",
                "--docs-pick", "pkg/a.py:1=2")
    _root, _before, (code, _out, err) = picked({"pkg/a.py": TABLES}, argv, TABLE_ENTRIES)
    assert code == 2
    assert err.splitlines() == [_ambiguous("pkg/a.py:16"), _unmatched("pkg/a.py:2"), _ambiguous("pkg/a.py:1=2")]


def test_a_kept_line_wins_over_its_pick(picked) -> None:
    argv = _map("--docs", "--docs-pick", "pkg/a.py:1=1", "--keep", "pkg/a.py:1")
    root, _before, (code, _out, err) = picked({"pkg/a.py": TABLES}, argv, TABLE_ENTRIES)
    assert code == 0
    assert read(root, "pkg/a.py").splitlines()[0] == '"""Every table lists its ``columns``."""'
    assert err == f"{leftover('pkg/a.py', 16, 'comment', 'columns')}\n"


def test_a_kept_literal_wins_over_its_pick(picked) -> None:
    body = BODY.replace('{"name": "orders",', '{"version": 3,')
    files = {"pkg/m.py": DS, "pkg/n.py": body, "pkg/o.py": 'from pkg.m import Ds\n\nD = Ds.model_validate({"version": 1, "columns": []})\n'}
    argv = _ds("--docs", "--docs-pick", "pkg/n.py:8", "--keep-literal", "version")
    root, _before, (code, _out, err) = picked(files, argv)
    assert (code, err) == (0, "")
    assert read(root, "pkg/n.py") == body


def test_a_patch_target_leftover_is_not_picked(picked) -> None:
    engine = "class SearchQueryEngine:\n    def save_model(self) -> None: ...\n"
    test = 'def test_t(mocker):\n    mocker.patch("pkg.engine.SearchQueryEngine.save_model")\n'
    argv = rename_argv("pkg/engine.py", "SearchQueryEngine", "QueryEngine", "--docs", "--docs-pick", "tests/test_t.py:2")
    root, before, (code, _out, err) = picked({"pkg/engine.py": engine, "tests/test_t.py": test}, argv)
    assert (code, err) == (2, f"{_unmatched('tests/test_t.py:2')}\n")
    assert file_tree(root) == before


def test_a_compound_declaration_line_is_not_picked(picked) -> None:
    files = {"pkg/models.py": "class Model:\n    pass\n", "pkg/names.py": "class ModelMeasures:\n    pass\n"}
    argv = rename_argv("pkg/models.py", "Model", "Dataset", "--docs", "--docs-pick", "pkg/names.py:1")
    root, before, (code, _out, err) = picked(files, argv)
    assert (code, err) == (2, f"{_unmatched('pkg/names.py:1')}\n")
    assert file_tree(root) == before
