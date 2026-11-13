"""The basedpyright language-server session in `python.lang`, against a fake server and the bundled one."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from project_files import file_tree

from living_architecture.lang import (
    PYRIGHT_PATCH_PRELOAD,
    LanguageServer,
    LanguageServerError,
    Span,
    utf16_index,
)

FAKE = Path(__file__).with_name("fake_lsp_server.py")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    return root.resolve()


@pytest.fixture
def record(tmp_path: Path) -> Path:
    return tmp_path / "record.jsonl"


def _fake(workspace: Path, record: Path, mode: str = "ok") -> LanguageServer:
    return LanguageServer(workspace, command=[sys.executable, str(FAKE), mode, str(record)])


def _records(record: Path) -> list[dict]:
    return [json.loads(line) for line in record.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize(
    ("text", "line", "character", "index"),
    [
        ("a😀b", 0, 3, 2),
        ("éx", 0, 1, 1),
        ("ab\r\ncd", 1, 1, 5),
        ("ab\ncd", 1, 2, 5),
        ("a\rb", 1, 0, 2),
        ("x\n😀😀y", 1, 4, 4),
    ],
    ids=["astral", "bmp-non-ascii", "crlf", "no-final-newline-end", "lone-cr", "astral-second-line"],
)
def test_utf16_positions_convert_to_character_indexes(text: str, line: int, character: int, index: int) -> None:
    assert utf16_index(text, line, character) == index


def test_session_runs_isolated_outside_the_workspace(workspace: Path, record: Path) -> None:
    with _fake(workspace, record) as server:
        server.open(workspace / "m.py", "x = 1\n")
        server.hover(workspace / "m.py", 0)
    [start] = [r for r in _records(record) if "cwd" in r]
    assert not Path(start["cwd"]).resolve().is_relative_to(workspace)
    env = start["env"]
    assert (env["PYTHONSAFEPATH"], env["PYTHONNOUSERSITE"], env["PYTHONDONTWRITEBYTECODE"]) == ("1", "1", "1")
    assert str(PYRIGHT_PATCH_PRELOAD) in env["NODE_OPTIONS"]
    assert not Path(env["LA_PYRIGHT_PATCH_RESULT"]).resolve().is_relative_to(workspace)
    assert file_tree(workspace) == {}


def test_configuration_requests_keep_the_projects_own_config(workspace: Path, record: Path) -> None:
    with _fake(workspace, record) as server:
        server.open(workspace / "m.py", "x = 1\n")
        server.hover(workspace / "m.py", 0)
    assert [r["configuration"] for r in _records(record) if "configuration" in r] == [[None, None]]


def test_query_positions_round_trip_through_utf16(workspace: Path, record: Path) -> None:
    path = workspace / "m.py"
    text = 's = "😀é"\r\nr: "Rec" = 1'
    offset = text.index("Rec")
    with _fake(workspace, record) as server:
        server.open(path, text)
        expected = [Span(path=path, start=offset, end=offset + 3)]
        assert server.references(path, offset) == expected
        assert server.definition(path, offset) == expected
        assert server.type_definition(path, offset) == expected
        assert server.hover(path, offset) == "(variable) x: Unknown"


@pytest.mark.parametrize("mode", ["fail-start", "unpatched"])
def test_a_server_that_fails_to_start_or_is_unpatched_is_an_error(workspace: Path, record: Path, mode: str) -> None:
    with pytest.raises(LanguageServerError), _fake(workspace, record, mode):
        pass


def test_a_server_exiting_mid_session_is_an_error(workspace: Path, record: Path) -> None:
    with _fake(workspace, record, "exit-on-query") as server:
        server.open(workspace / "m.py", "x = 1\n")
        with pytest.raises(LanguageServerError):
            server.references(workspace / "m.py", 0)


def test_closing_a_server_that_is_still_exiting_is_quiet(
    workspace: Path, record: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _fake(workspace, record, "exit-on-query") as server:
        server.open(workspace / "m.py", "x = 1\n")
        with pytest.raises(LanguageServerError):
            server.references(workspace / "m.py", 0)
        time.sleep(0.2)
        monkeypatch.setattr(subprocess.Popen, "poll", lambda _self: None)


def test_bundled_server_finds_forward_reference_strings(workspace: Path) -> None:
    path = workspace / "m.py"
    text = 'class Rec:\n    pass\n\n\ndef make() -> "Rec":\n    return Rec()\n'
    path.write_text(text, encoding="utf-8")
    before = file_tree(workspace)
    with LanguageServer(workspace) as server:
        server.open(path, text)
        spans = server.references(path, text.index("Rec"))
    assert sorted((s.start, s.end) for s in spans) == [
        (i, i + 3) for i in (text.index("Rec"), text.index('"Rec"') + 1, text.rindex("Rec"))
    ]
    assert file_tree(workspace) == before


def test_bundled_server_that_cannot_start_is_an_error(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NODE_OPTIONS", "--require /nonexistent.js")
    with pytest.raises(LanguageServerError), LanguageServer(workspace):
        pass
