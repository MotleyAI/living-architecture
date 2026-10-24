import json
from pathlib import Path
from typing import Any

import pytest

from living_architecture import config
from living_architecture.cli import la_config as main
from living_architecture.config import CONFIG_FILENAME, format_value


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / CONFIG_FILENAME).write_text(
        f"format: {config.current_format()}\n"
        "reviewers:\n  codex: false\n  sonar: {project_key: k}\n"
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
    assert main(["--root", str(repo), "get", "reviewers.codex"]) == 0
    assert capsys.readouterr().out == "false\n"


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
    assert data["reviewers"] == {"codex": False, "sonar": {"project_key": "k"}}


def test_defaults_without_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--root", str(tmp_path), "get", "tracker"]) == 0
    assert capsys.readouterr().out == "linear\n"


def test_invalid_config_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / CONFIG_FILENAME).write_text(f"format: {config.current_format()}\nbogus: 1\n", encoding="utf-8")
    assert main(["--root", str(tmp_path), "show"]) == 1
    assert "bogus" in capsys.readouterr().err


def test_show_notes_each_local_key_on_stderr(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "living-architecture.local.yaml").write_text("reviewers: {codex: true}\ntracker: none\n", encoding="utf-8")
    assert main(["--root", str(repo), "show"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out)["tracker"] == "none"
    assert captured.err == (
        "la-config: tracker from living-architecture.local.yaml\n"
        "la-config: reviewers.codex from living-architecture.local.yaml\n"
    )


def test_show_reads_the_local_file_once(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    local = repo / "living-architecture.local.yaml"
    local.write_text("tracker: none\n", encoding="utf-8")
    reads: list[Path] = []
    read_text = Path.read_text

    def counting(path: Path, *args: Any, **kwargs: Any) -> str:
        reads.append(path)
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting)
    assert main(["--root", str(repo), "show"]) == 0
    assert reads.count(local) == 1
    assert "tracker from" in capsys.readouterr().err


def test_get_prints_no_local_note(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "living-architecture.local.yaml").write_text("tracker: none\n", encoding="utf-8")
    assert main(["--root", str(repo), "get", "tracker"]) == 0
    assert capsys.readouterr() == ("none\n", "")


def test_refused_local_key_exits_1(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "living-architecture.local.yaml").write_text("openspec: false\n", encoding="utf-8")
    assert main(["--root", str(repo), "show"]) == 1
    err = capsys.readouterr().err
    assert "openspec" in err
    assert "living-architecture.local.yaml" in err
