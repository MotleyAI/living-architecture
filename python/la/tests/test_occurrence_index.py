"""The Python occurrence index: a run's language-server requests do not grow with its entries or occurrences, and a
module refactor starts no server."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml
from project_files import write_project
from refactor_cli import read, run

from living_architecture.lang import LanguageServer

EXPORT = "la.exportOccurrences"
PER_OCCURRENCE = ("textDocument/references", "textDocument/hover", "textDocument/definition",
                  "textDocument/typeDefinition")
NAMES = [f"fn{i}" for i in range(10)]
LIB = "".join(f"def {name}() -> int:\n    return {i}\n\n\n" for i, name in enumerate(NAMES))
USE = "from pkg.lib import " + ", ".join(NAMES) + "\n\n\ndef total() -> int:\n    return " + " + ".join(
    f"{name}() + {name}()" for name in NAMES) + "\n"
MEMBERS = "class Box:\n    def fn0(self) -> int:\n        return 0\n\n\ndef peek(b: Box) -> object:\n    return getattr(b, \"fn0\")\n"


class Requests:
    """Every request a language server is sent, by method (an executed command by its name), and the servers
    started."""

    def __init__(self) -> None:
        self.sent: Counter[str] = Counter()
        self.starts = 0

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        request, enter = LanguageServer._request, LanguageServer.__enter__  # pyright: ignore[reportPrivateUsage]

        def counting(server: LanguageServer, method: str, params: Any) -> Any:
            command = params.get("command") if method == "workspace/executeCommand" else None
            self.sent[command or method] += 1
            return request(server, method, params)

        def starting(server: LanguageServer) -> LanguageServer:
            self.starts += 1
            return enter(server)

        monkeypatch.setattr(LanguageServer, "_request", counting)
        monkeypatch.setattr(LanguageServer, "__enter__", starting)

    def per_occurrence(self) -> dict[str, int]:
        return {m: n for m, n in self.sent.items() if m in PER_OCCURRENCE}


def _map(entries: Sequence[Mapping[str, object]]) -> str:
    return yaml.safe_dump(list(entries), sort_keys=False)


def _counted(tmp_path: Path, name: str, files: dict[str, str], argv: list[str], monkeypatch: pytest.MonkeyPatch,
             capsys: pytest.CaptureFixture[str]) -> tuple[Requests, tuple[int, str, str], Path]:
    root = write_project(tmp_path / name, files)
    requests = Requests()
    with monkeypatch.context() as patched:
        requests.install(patched)
        result = run(root, argv, patched, capsys)
    return requests, result, root


@pytest.mark.parametrize(("members", "exports"), [(False, 2), (True, 3)], ids=["symbols", "with-string-members"])
def test_export_requests_do_not_grow_with_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], members: bool, exports: int
) -> None:
    # The self-test and one export, plus one fixed probe round when a file holds string-member calls.
    files = {"pkg/lib.py": LIB, "pkg/use.py": USE, **({"pkg/box.py": MEMBERS} if members else {})}
    counts = []
    for size in (1, 10):
        entries = [{"file": "pkg/lib.py", "symbol": name, "new_name": f"renamed{i}"} for i, name in enumerate(NAMES[:size])]
        requests, (code, _out, err), root = _counted(
            tmp_path, f"map{size}", {**files, "map.yaml": _map(entries)}, ["--apply", "rename-map", "map.yaml"],
            monkeypatch, capsys)
        assert (code, err) == (0, ""), err
        assert requests.per_occurrence() == {}
        assert requests.starts == 1
        counts.append(requests.sent[EXPORT])
        expected = LIB
        for i, name in enumerate(NAMES[:size]):
            expected = expected.replace(f"def {name}(", f"def renamed{i}(")
        assert read(root, "pkg/lib.py") == expected
    assert counts == [exports, exports]


ROPE_ONLY = {
    "pkg/a.py": "def foo() -> int:\n    return 1\n",
    "scripts/use.py": "from pkg.a import foo\n\nfoo()\n",
    "pyrightconfig.json": '{"executionEnvironments": [{"root": "scripts"}]}\n',
}


def test_a_map_with_an_entry_rope_resolves_sends_the_same_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    entries = [{"file": "pkg/a.py", "symbol": "foo", "new_name": "bar"}]
    requests, (code, out, err), _root = _counted(
        tmp_path, "rope", {**ROPE_ONLY, "map.yaml": _map(entries)}, ["rename-map", "map.yaml"], monkeypatch, capsys)
    assert (code, err) == (0, ""), err
    assert "+from pkg.a import bar\n" in out
    assert "+bar()\n" in out
    resolved, (code, _out, err), _root = _counted(
        tmp_path, "resolved", {**{k: v for k, v in ROPE_ONLY.items() if k != "pyrightconfig.json"},
                               "map.yaml": _map(entries)}, ["rename-map", "map.yaml"], monkeypatch, capsys)
    assert (code, err) == (0, ""), err
    assert requests.per_occurrence() == {}
    assert (requests.starts, requests.sent[EXPORT]) == (1, 2)
    assert requests.sent == resolved.sent


KINDS = 'from typing import Literal\n\nDriftKind = Literal["edit_model", "drop"]\n'
KIND_USE = ('from pkg.kinds import DriftKind\n\n\ndef f(kind: DriftKind) -> None:\n    print(kind)\n\n\n'
            'def call() -> None:\n    f("edit_model")\n    f("drop")\n')


def test_literal_entries_keep_their_probe_count_on_the_one_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    entries = [{"file": "pkg/kinds.py", "symbol": "DriftKind['edit_model']", "new_name": "edit_master"},
               {"file": "pkg/kinds.py", "symbol": "DriftKind['drop']", "new_name": "discard"}]
    requests, (code, _out, err), _root = _counted(
        tmp_path, "literal", {"pkg/kinds.py": KINDS, "pkg/use.py": KIND_USE, "map.yaml": _map(entries)},
        ["rename-map", "map.yaml"], monkeypatch, capsys)
    assert (code, err) == (0, ""), err
    others = {m: n for m, n in requests.sent.items() if m != EXPORT}
    assert (requests.starts, others) == (1, {"initialize": 1, "textDocument/diagnostic": 8})
    assert requests.sent[EXPORT] <= 2


CLIENT = "def run() -> int:\n    return 1\n"
CLIENT_USE = "from pkg import client\n\n\ndef g() -> int:\n    return client.run()\n"


@pytest.mark.parametrize(
    "argv",
    [
        ["rename", "--file", "pkg/use.py", "--symbol", "client", "--new-name", "cli2"],
        ["move-module", "--module", "pkg/client.py", "--dest", "pkg/sub"],
        ["move-symbol", "--file", "pkg/client.py", "--symbol", "run", "--dest", "pkg/other.py"],
    ],
    ids=["module-rename", "move-module", "move-symbol"],
)
def test_module_refactors_and_moves_start_no_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    files = {"pkg/client.py": CLIENT, "pkg/use.py": CLIENT_USE, "pkg/other.py": "", "pkg/sub/__init__.py": ""}
    requests, (code, _out, err), _root = _counted(tmp_path, "mod", files, argv, monkeypatch, capsys)
    assert (code, err) == (0, ""), err
    assert (requests.starts, dict(requests.sent)) == (0, {})
