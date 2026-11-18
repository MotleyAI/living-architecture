"""Python renames, of symbols and of modules, build no rope project, renamer or change set."""

from __future__ import annotations

from pathlib import Path

import pytest
from project_files import write_project
from refactor_cli import run
from rope.base.change import ChangeSet
from rope.base.project import Project
from rope.refactor.rename import Rename


@pytest.fixture(autouse=True)
def no_rope(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: object, **__: object) -> None:
        raise AssertionError("a rename used rope")

    for cls in (Project, Rename, ChangeSet):
        monkeypatch.setattr(cls, "__init__", refuse)


def test_a_symbol_rename_map_uses_no_rope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                          capsys: pytest.CaptureFixture[str]) -> None:
    root = write_project(tmp_path / "proj", {
        "pkg/a.py": "def foo() -> int:\n    return 1\n\n\nclass Box:\n    size: int = 0\n",
        "pkg/b.py": "from pkg.a import Box, foo\n\n\ndef use(b: Box) -> int:\n    return foo() + b.size\n",
        "map.yaml": "- {file: pkg/a.py, symbol: foo, new_name: bar}\n- {file: pkg/a.py, symbol: Box.size, new_name: width}\n",
    })
    code, _out, err = run(root, ["--apply", "rename-map", "map.yaml"], monkeypatch, capsys)
    assert (code, err) == (0, ""), err
    assert (root / "pkg" / "b.py").read_text(encoding="utf-8") == (
        "from pkg.a import Box, bar\n\n\ndef use(b: Box) -> int:\n    return bar() + b.width\n")


def test_a_module_rename_uses_no_rope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                      capsys: pytest.CaptureFixture[str]) -> None:
    root = write_project(tmp_path / "proj", {"pkg/client.py": "X = 1\n",
                                             "pkg/use.py": "from pkg import client\n\nprint(client.X)\n"})
    argv = ["--apply", "rename", "--file", "pkg/use.py", "--symbol", "client", "--new-name", "cli2"]
    code, _out, err = run(root, argv, monkeypatch, capsys)
    assert (code, err) == (0, ""), err
    assert (root / "pkg" / "cli2.py").is_file()
    assert (root / "pkg" / "use.py").read_text(encoding="utf-8") == "from pkg import cli2\n\nprint(cli2.X)\n"
