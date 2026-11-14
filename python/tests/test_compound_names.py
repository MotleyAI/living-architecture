"""Python `--docs` lists declarations whose name contains the old name as a word sequence."""

from __future__ import annotations

from pathlib import Path

import pytest
from project_files import write_project
from refactor_cli import read, run

from living_architecture.contract import message

MODELS = "class Model:\n    pass\n"
NAMES = """\
from pkg.models import Model


class ModelMeasures:
    pass


class AcmeModels:
    pass


class TestModelMeasurePosition:
    pass


def lookup(model_name: str) -> Model:
    return Model()


Modelling = 1
"""


def _rename(rel: str, symbol: str, new: str, *flags: str) -> list[str]:
    return ["--apply", "rename", "--file", rel, "--symbol", symbol, "--new-name", new, *flags]


def _compound(path: str, line: int, name: str, old: str) -> str:
    return message("refactor.compound", path=path, line=line, name=name, old=old)


def test_compound_names_listed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_project(tmp_path / "proj", {"pkg/models.py": MODELS, "pkg/names.py": NAMES})
    code, _out, err = run(root, _rename("pkg/models.py", "Model", "Dataset", "--docs"), monkeypatch, capsys)
    assert code == 0
    assert err.splitlines() == [
        _compound("pkg/names.py", 4, "ModelMeasures", "Model"),
        _compound("pkg/names.py", 8, "AcmeModels", "Model"),
        _compound("pkg/names.py", 12, "TestModelMeasurePosition", "Model"),
        _compound("pkg/names.py", 16, "model_name", "Model"),
    ]
    assert "class ModelMeasures:" in read(root, "pkg/names.py")
    assert "def lookup(model_name: str) -> Dataset:" in read(root, "pkg/names.py")


SNAKE = """\
def column() -> int:
    return 1


def get_columns() -> list[int]:
    return [column()]


class ColumnCycleError(Exception):
    pass
"""


def test_snake_case_and_plural(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_project(tmp_path / "proj", {"pkg/cols.py": SNAKE})
    code, _out, err = run(root, _rename("pkg/cols.py", "column", "field", "--docs"), monkeypatch, capsys)
    assert code == 0
    assert err.splitlines() == [
        _compound("pkg/cols.py", 5, "get_columns", "column"),
        _compound("pkg/cols.py", 9, "ColumnCycleError", "column"),
    ]


ES_PLURAL = "class Box:\n    pass\n\n\nboxes: list[Box] = []\nboxer = 1\n"


def test_es_plural_of_the_last_word(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_project(tmp_path / "proj", {"pkg/box.py": ES_PLURAL})
    code, _out, err = run(root, _rename("pkg/box.py", "Box", "Crate", "--docs"), monkeypatch, capsys)
    assert code == 0
    assert err.splitlines() == [_compound("pkg/box.py", 5, "boxes", "Box")]


def test_without_docs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = write_project(tmp_path / "proj", {"pkg/models.py": MODELS, "pkg/names.py": NAMES})
    assert run(root, _rename("pkg/models.py", "Model", "Dataset"), monkeypatch, capsys)[::2] == (0, "")


ACRONYM = "class Http:\n    pass\n\n\nclass HTTPServer:\n    pass\n\n\nclass Httpx:\n    pass\n"


def test_a_run_of_capitals_is_one_word(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/m.py": ACRONYM})
    code, _out, err = run(root, _rename("pkg/m.py", "Http", "Web", "--docs"), monkeypatch, capsys)
    assert code == 0
    assert err.splitlines() == [_compound("pkg/m.py", 5, "HTTPServer", "Http")]


def test_retarget_lists_compound_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {
        "pkg/models.py": "class Model:\n    pass\n\n\nAcmeModel = Model\n\n\nclass AcmeModelCache:\n    pass\n",
    })
    argv = ["--apply", "retarget", "--file", "pkg/models.py", "--symbol", "AcmeModel", "--target", "Model", "--docs"]
    code, _out, err = run(root, argv, monkeypatch, capsys)
    assert code == 0
    assert err.splitlines() == [_compound("pkg/models.py", 8, "AcmeModelCache", "AcmeModel")]
