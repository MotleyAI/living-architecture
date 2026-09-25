import json
from pathlib import Path

import pytest

from living_architecture.config import CONFIG_FILENAME
from living_architecture.config_cli import format_value, main


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / CONFIG_FILENAME).write_text(
        "reviewers:\n  coderabbit: true\n  sonar: {enabled: true, project_key: k}\n"
        "conventions: {exempt: [a.py]}\n",
        encoding="utf-8",
    )
    return tmp_path


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, "true"), (False, "false"), (None, ""), ("x y", "x y"), (0.15, "0.15"), (["a"], '["a"]')],
)
def test_format_value(value: object, expected: str) -> None:
    assert format_value(value) == expected


def test_get_bool(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--root", str(repo), "get", "reviewers.coderabbit"]) == 0
    assert capsys.readouterr().out == "true\n"


def test_get_nested_string(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--root", str(repo), "get", "reviewers.sonar.project_key"]) == 0
    assert capsys.readouterr().out == "k\n"


def test_get_list_is_json(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--root", str(repo), "get", "conventions.exempt"]) == 0
    assert json.loads(capsys.readouterr().out) == ["a.py"]


def test_get_unset_is_empty(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--root", str(repo), "get", "commands.test"]) == 0
    assert capsys.readouterr().out == "\n"


def test_get_unknown_key(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--root", str(repo), "get", "reviewers.nope"]) == 2
    assert "unknown key" in capsys.readouterr().err


def test_show(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--root", str(repo), "show"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["reviewers"]["sonar"] == {"enabled": True, "project_key": "k"}


def test_defaults_without_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--root", str(tmp_path), "get", "reviewers.sonar.enabled"]) == 0
    assert capsys.readouterr().out == "false\n"


def test_invalid_config_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / CONFIG_FILENAME).write_text("bogus: 1\n", encoding="utf-8")
    assert main(["--root", str(tmp_path), "show"]) == 1
    assert "bogus" in capsys.readouterr().err
