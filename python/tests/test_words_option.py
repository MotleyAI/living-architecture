"""Python `--words TABLE` on a rename: carve-outs leave matching stand-ins and list the `--docs` mentions they cover."""

from __future__ import annotations

from pathlib import Path

import pytest
from project_files import write_project
from refactor_cli import read, run

from living_architecture.contract import message

SOURCE = '''\
class Ds:
    """Holds ``columns``."""

    columns: list[str] = []


class Probe:
    """Probes ``columns``."""

    columns: list[str] = []
'''
RENAME = ["--apply", "rename", "--file", "pkg/c.py", "--symbol", "Ds.columns", "--new-name", "fields", "--words", "words.yaml"]
WORDS = "words:\n- {from: columns, to: fields}\n- {from: rows, to: records}\n"
PROBE = WORDS + "carve_outs:\n- words: [columns]\n  symbols:\n  - {file: pkg/c.py, symbol: Probe.columns}\n"
DS_RENAMED = 'class Ds:\n    """Holds ``fields``."""\n\n    fields: list[str] = []\n'


def _stand_in(line: int, cls: str) -> str:
    return message("refactor.stand-in", path="pkg/c.py", line=line, cls=cls, attr="columns") + "\n"


def _leftover(line: int) -> str:
    return message("refactor.leftover", path="pkg/c.py", line=line, where="docstring", old="columns") + "\n"


def test_a_stand_in_a_symbols_carve_out_locates_is_left(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/c.py": SOURCE, "words.yaml": PROBE})
    code, _out, err = run(root, RENAME, monkeypatch, capsys)
    assert (code, err, read(root, "pkg/c.py")) == (0, "", SOURCE.replace("    columns: list[str] = []\n", "    fields: list[str] = []\n", 1))


def test_a_carve_out_for_another_word_leaves_no_stand_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    table = WORDS + "carve_outs:\n- {words: [rows], paths: ['pkg/**']}\n"
    root = write_project(tmp_path / "proj", {"pkg/c.py": SOURCE, "words.yaml": table})
    assert run(root, RENAME, monkeypatch, capsys) == (1, "", _stand_in(10, "Probe"))


def test_with_renames_a_carved_stand_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/c.py": SOURCE, "words.yaml": PROBE})
    code, _out, err = run(root, [*RENAME, "--with", "pkg/c.py:10"], monkeypatch, capsys)
    assert (code, err, read(root, "pkg/c.py").count("fields: list[str] = []")) == (0, "", 2)


def test_a_mention_inside_the_class_of_a_carved_member_is_listed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/c.py": SOURCE, "words.yaml": PROBE})
    code, _out, err = run(root, [*RENAME, "--docs"], monkeypatch, capsys)
    assert (code, err, read(root, "pkg/c.py")) == (0, _leftover(8), SOURCE.replace(SOURCE[: SOURCE.index("\n\n\n") + 1], DS_RENAMED))


CENSUS = SOURCE[: SOURCE.index("\n\n\n") + 1] + '''

def census(all_columns: list[IntrospectedColumn]) -> int:
    """Counts ``columns``."""
    return len(all_columns)
'''


def test_a_carved_declaration_whose_name_only_holds_the_old_name_covers_no_mention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    table = WORDS + "carve_outs:\n- {words: [columns], annotated: [IntrospectedColumn]}\n"
    root = write_project(tmp_path / "proj", {"pkg/c.py": CENSUS, "words.yaml": table})
    code, _out, err = run(root, [*RENAME, "--docs"], monkeypatch, capsys)
    compound = message("refactor.compound", path="pkg/c.py", line=7, name="all_columns", old="columns") + "\n"
    assert (code, err, read(root, "pkg/c.py")) == (
        0, compound, CENSUS.replace(CENSUS[: CENSUS.index("\n\n\n") + 1], DS_RENAMED).replace("Counts ``columns``", "Counts ``fields``"))


FIXTURE = "import pytest\n\n\nclass TestC:\n    @pytest.fixture\n    def columns(self) -> list[str]:\n        return []\n"
DS_ONLY = SOURCE[: SOURCE.index("\n\n\n") + 1]


@pytest.mark.parametrize("flags", [["--with", "--without"], ["--without", "--with"]], ids=["with-first", "without-first"])
def test_with_wins_over_without_on_a_stand_in_left_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], flags: list[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/c.py": DS_ONLY, "tests/test_c.py": FIXTURE, "words.yaml": WORDS})
    sites = [part for flag in flags for part in (flag, "tests/test_c.py:6")]
    code, _out, err = run(root, [*RENAME, *sites], monkeypatch, capsys)
    assert (code, err, read(root, "tests/test_c.py")) == (0, "", FIXTURE.replace("def columns", "def fields"))


MODULE_LEVEL = SOURCE + "\n\ncolumns: list[str] = []\n"


def test_a_carved_module_level_name_covers_every_mention_of_its_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    table = WORDS + "carve_outs:\n- words: [columns]\n  symbols:\n  - {file: pkg/c.py, symbol: columns}\n"
    root = write_project(tmp_path / "proj", {"pkg/c.py": MODULE_LEVEL, "words.yaml": table})
    code, _out, err = run(root, [*RENAME, "--docs", "--without", "pkg/c.py:10"], monkeypatch, capsys)
    assert (code, err, read(root, "pkg/c.py")) == (
        0, _leftover(2) + _leftover(8), MODULE_LEVEL.replace("    columns: list[str] = []\n", "    fields: list[str] = []\n", 1))


def test_without_words_every_code_marked_mention_of_the_declaring_file_is_rewritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/c.py": SOURCE})
    argv = [*RENAME[:-2], "--docs", "--without", "pkg/c.py:10"]
    code, _out, err = run(root, argv, monkeypatch, capsys)
    assert (code, err, read(root, "pkg/c.py").count("``fields``")) == (0, "", 2)
