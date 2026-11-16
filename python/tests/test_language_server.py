"""The basedpyright language-server session in `python.lang`, against a fake server and the bundled one."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from project_files import file_tree

from living_architecture.lang import (
    PYRIGHT_EXPORT_PRELOAD,
    PYRIGHT_PATCH_PRELOAD,
    ExportRequest,
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


def test_session_runs_isolated_outside_the_workspace(
    workspace: Path, record: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYTHONPATH", str(workspace))
    with _fake(workspace, record) as server:
        server.open(workspace / "m.py", "x = 1\n")
        server.definition(workspace / "m.py", 0)
    [start] = [r for r in _records(record) if "cwd" in r]
    assert not Path(start["cwd"]).resolve().is_relative_to(workspace)
    env = start["env"]
    assert (env["PYTHONSAFEPATH"], env["PYTHONNOUSERSITE"], env["PYTHONDONTWRITEBYTECODE"]) == ("1", "1", "1")
    assert env["PYTHONPATH"] is None
    assert str(PYRIGHT_PATCH_PRELOAD) in env["NODE_OPTIONS"]
    assert not Path(env["LA_PYRIGHT_PATCH_RESULT"]).resolve().is_relative_to(workspace)
    assert file_tree(workspace) == {}


def test_configuration_requests_keep_the_projects_own_config(workspace: Path, record: Path) -> None:
    with _fake(workspace, record) as server:
        server.open(workspace / "m.py", "x = 1\n")
        server.definition(workspace / "m.py", 0)
    assert [r["configuration"] for r in _records(record) if "configuration" in r] == [[None, None]]


def test_query_positions_round_trip_through_utf16(workspace: Path, record: Path) -> None:
    path = workspace / "m.py"
    text = 's = "😀é"\r\nr: "Rec" = 1'
    offset = text.index("Rec")
    with _fake(workspace, record) as server:
        server.open(path, text)
        expected = [Span(path=path, start=offset, end=offset + 3)]
        assert server.definition(path, offset) == expected


def test_percent_signs_in_paths_are_decoded_once(workspace: Path, record: Path) -> None:
    path = workspace / "repo%20copy" / "m.py"
    with _fake(workspace, record) as server:
        server.open(path, "x = 1\n")
        assert server.definition(path, 0) == [Span(path=path, start=0, end=3)]


class _TrickleStdin:
    """A pipe that accepts at most two bytes per write."""

    def __init__(self) -> None:
        self.data = b""

    def write(self, data: bytes | memoryview) -> int:
        self.data += bytes(data[:2])
        return min(2, len(data))

    def flush(self) -> None:
        pass


def test_short_writes_still_send_the_whole_frame(workspace: Path) -> None:
    stdin = _TrickleStdin()
    proc = cast(subprocess.Popen[bytes], SimpleNamespace(stdin=stdin))
    LanguageServer(workspace, command=["unused"])._send({"jsonrpc": "2.0", "method": "x"}, proc)
    body = b'{"jsonrpc": "2.0", "method": "x"}'
    assert stdin.data == b"Content-Length: %d\r\n\r\n" % len(body) + body


@pytest.mark.parametrize("mode", ["fail-start", "unpatched"])
def test_a_server_that_fails_to_start_or_is_unpatched_is_an_error(workspace: Path, record: Path, mode: str) -> None:
    with pytest.raises(LanguageServerError), _fake(workspace, record, mode):
        pass


def test_a_server_exiting_mid_session_is_an_error(workspace: Path, record: Path) -> None:
    with _fake(workspace, record, "exit-on-query") as server:
        server.open(workspace / "m.py", "x = 1\n")
        with pytest.raises(LanguageServerError):
            server.definition(workspace / "m.py", 0)


def test_closing_a_server_that_is_still_exiting_is_quiet(
    workspace: Path, record: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _fake(workspace, record, "exit-on-query") as server:
        server.open(workspace / "m.py", "x = 1\n")
        with pytest.raises(LanguageServerError):
            server.definition(workspace / "m.py", 0)
        time.sleep(0.2)
        monkeypatch.setattr(subprocess.Popen, "poll", lambda _self: None)


def test_bundled_server_pulls_diagnostics_of_the_current_text(workspace: Path) -> None:
    path = workspace / "m.py"
    text = 'x: int = 1\n'
    path.write_text(text, encoding="utf-8")
    with LanguageServer(workspace) as server:
        server.open(path, text)
        assert server.diagnostics(path) == []
        changed = 'x: int = "a😀"\n'
        server.change(path, changed)
        found = server.diagnostics(path)
    assert [(d.code, d.severity, d.span.start, d.span.end) for d in found] == [
        ("reportAssignmentType", 1, changed.index('"'), len(changed) - 1)
    ]


def test_bundled_server_that_cannot_start_is_an_error(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NODE_OPTIONS", "--require /nonexistent.js")
    with pytest.raises(LanguageServerError), LanguageServer(workspace):
        pass


# ---- the occurrence export


def _word_spans(text: str, name: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in re.finditer(rf"(?<!\w){name}(?!\w)", text)]


def test_session_loads_the_export_preload_and_self_tests_the_command_once(workspace: Path, record: Path) -> None:
    with _fake(workspace, record):
        pass
    records = _records(record)
    [start] = [r for r in records if "cwd" in r]
    env = start["env"]
    assert str(PYRIGHT_PATCH_PRELOAD) in env["NODE_OPTIONS"]
    assert str(PYRIGHT_EXPORT_PRELOAD) in env["NODE_OPTIONS"]
    assert not Path(env["LA_PYRIGHT_EXPORT_RESULT"]).resolve().is_relative_to(workspace)
    [command] = [r for r in records if "command" in r]
    assert command["command"] == "la.exportOccurrences"
    assert (command["arguments"][0]["names"], command["arguments"][0]["files"]) == ([], [])
    assert file_tree(workspace) == {}


@pytest.mark.parametrize("mode", ["no-export", "export-null", "export-unverified"])
def test_a_server_whose_export_fails_its_self_test_is_an_error(workspace: Path, record: Path, mode: str) -> None:
    with pytest.raises(LanguageServerError), _fake(workspace, record, mode):
        pass


@pytest.mark.parametrize(
    "text",
    [
        'class Rec:\r\n    pass\r\n\r\nr: "Rec" = Rec()\r\n',
        "x = 1\rRec = 2\ry = Rec\n",
        's = "😀"; Rec = 1\nt = "a😀b😀"; u = Rec',
        'v = "😀Rec😀"; w = "é"\r\nRec = 1\r',
    ],
    ids=["crlf", "lone-cr", "astral-before", "astral-around"],
)
def test_export_spans_convert_against_the_opened_text(workspace: Path, record: Path, text: str) -> None:
    path = workspace / "m.py"
    with _fake(workspace, record) as server:
        server.open(path, text)
        index = server.export(ExportRequest(names=["Rec"], files=[path]))
    assert sorted((o.span.start, o.span.end) for o in index.occurrences) == _word_spans(text, "Rec")
    assert {(o.span.path, o.name) for o in index.occurrences} == {(path, "Rec")}


def test_an_exported_span_off_the_old_name_is_an_error(workspace: Path, record: Path) -> None:
    path = workspace / "m.py"
    request = ExportRequest(names=["Rec"], files=[path])
    with _fake(workspace, record, "bad-range") as server:
        server.open(path, "Rec = 1\n")
        with pytest.raises(LanguageServerError):
            server.export(request)


def test_bundled_server_exports_name_occurrences_with_kinds_and_declarations(workspace: Path) -> None:
    path = workspace / "m.py"
    text = '__all__ = ["Rec"]\n\n\nclass Rec:\n    pass\n\n\ndef make() -> "Rec":\n    return Rec()\n'
    path.write_text(text, encoding="utf-8")
    before = file_tree(workspace)
    with LanguageServer(workspace) as server:
        server.open(path, text)
        index = server.export(ExportRequest(names=["Rec"], files=[path]))
    declared = text.index("class Rec") + len("class ")
    assert sorted((o.span.start, o.kind) for o in index.occurrences) == [
        (text.index('"Rec"') + 1, "all-entry"),
        (declared, "name"),
        (text.index('"Rec":') + 1, "forward-reference"),
        (text.rindex("Rec"), "name"),
    ]
    for o in index.occurrences:
        if o.kind != "all-entry":
            assert [(d.span.path, d.span.start) for d in o.declarations] == [(path, declared)]
    assert file_tree(workspace) == before


def test_bundled_server_exports_the_import_bindings_an_occurrence_passes_through(workspace: Path) -> None:
    pkg = workspace / "pkg"
    pkg.mkdir()
    texts = {
        "__init__.py": "",
        "core.py": "class Model:\n    pass\n",
        "compat.py": 'from pkg.core import Model as AcmeModel\n\n__all__ = ["AcmeModel"]\n',
        "other.py": "from pkg.core import Model as AcmeModel\n\nb = AcmeModel()\n",
        "use.py": "from pkg.compat import AcmeModel\n\na = AcmeModel()\n",
    }
    for name, text in texts.items():
        (pkg / name).write_text(text, encoding="utf-8")
    files = [pkg / name for name in texts]
    with LanguageServer(workspace) as server:
        for path in files:
            server.open(path, texts[path.name])
        index = server.export(ExportRequest(names=["AcmeModel"], files=files))
    compat = (pkg / "compat.py", texts["compat.py"].index("AcmeModel"))
    other = (pkg / "other.py", texts["other.py"].index("AcmeModel"))
    use = (pkg / "use.py", texts["use.py"].index("AcmeModel"))
    chains = sorted((o.span.path.name, o.span.start, [(b.path, b.start) for b in o.bindings]) for o in index.occurrences)
    assert chains == [
        ("compat.py", compat[1], [compat]),
        ("compat.py", texts["compat.py"].index('"AcmeModel"') + 1, [compat]),
        ("other.py", other[1], [other]),
        ("other.py", texts["other.py"].rindex("AcmeModel"), [other]),
        ("use.py", use[1], [use, compat]),
        ("use.py", texts["use.py"].rindex("AcmeModel"), [use, compat]),
    ]
    model = (pkg / "core.py", texts["core.py"].index("Model"))
    assert {(d.span.path, d.span.start) for o in index.occurrences for d in o.declarations} == {model}


def test_bundled_server_exports_member_receiver_verdicts(workspace: Path) -> None:
    path = workspace / "m.py"
    text = (
        "from typing import Any\n\n\nclass A:\n    def run(self) -> int:\n        return 1\n\n\n"
        "def typed(a: A) -> int:\n    return a.run()\n\n\n"
        "def untyped(o):\n    return o.run()\n\n\n"
        "def anything(o: Any) -> int:\n    return o.run()\n"
    )
    path.write_text(text, encoding="utf-8")
    with LanguageServer(workspace) as server:
        server.open(path, text)
        index = server.export(ExportRequest(names=["run"], files=[path]))
    accesses = [m.start() for m in re.finditer(r"\.run\(", text)]
    members = sorted((o.span.start, o.receiver) for o in index.occurrences if o.kind == "member")
    assert members == [(accesses[0] + 1, None), (accesses[1] + 1, "Unknown"), (accesses[2] + 1, "Any")]
    [typed] = [o for o in index.occurrences if o.span.start == accesses[0] + 1]
    assert [(d.span.path, d.span.start) for d in typed.declarations] == [(path, text.index("def run") + len("def "))]
