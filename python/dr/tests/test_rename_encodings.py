"""Python renames, symbol and module, write each file back in its own encoding with every line ending kept."""

from __future__ import annotations

from pathlib import Path

import pytest

from project_files import write_project
from refactor_cli import run

# Each importer's bytes, spelling the renamed name as OLD.
IMPORTERS: dict[str, bytes] = {
    "utf8-bom": b"\xef\xbb\xbffrom pkg.mod import OLD\n\nprint(OLD)\n",
    "utf8-cookie": "# -*- coding: utf-8 -*-\nfrom pkg.mod import OLD\n\ns = 'é😀'\nprint(OLD, s)\n".encode(),
    "latin1-cookie": "# coding: latin-1\nfrom pkg.mod import OLD\n\ns = 'é'\nprint(OLD, s)\n".encode("latin-1"),
    "crlf": b"from pkg.mod import OLD\r\n\r\nprint(OLD)\r\n",
    "lone-cr": b"from pkg.mod import OLD\r\rprint(OLD)\r",
    "mixed": b"from pkg.mod import OLD\r\nimport os\n\r\nprint(OLD, os.sep)\n",
    "no-final-newline": b"from pkg.mod import OLD\n\nprint(OLD)",
}


@pytest.mark.parametrize("vector", sorted(IMPORTERS))
def test_a_symbol_rename_keeps_each_files_encoding_and_line_endings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], vector: str
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/mod.py": "def foo() -> int:\n    return 1\n"})
    data = IMPORTERS[vector].replace(b"OLD", b"foo")
    (root / "pkg" / "use.py").write_bytes(data)
    argv = ["--apply", "rename", "--file", "pkg/mod.py", "--symbol", "foo", "--new-name", "bar"]
    assert run(root, argv, monkeypatch, capsys)[0] == 0
    assert (root / "pkg" / "use.py").read_bytes() == data.replace(b"foo", b"bar")


@pytest.mark.parametrize("vector", sorted(IMPORTERS))
def test_a_module_rename_keeps_each_files_encoding_and_line_endings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], vector: str
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/client.py": "X = 1\n"})
    data = IMPORTERS[vector].replace(b"from pkg.mod import OLD", b"from pkg import OLD").replace(b"OLD", b"client")
    (root / "pkg" / "use.py").write_bytes(data)
    argv = ["--apply", "rename", "--file", "pkg/use.py", "--symbol", "client", "--new-name", "cli2"]
    assert run(root, argv, monkeypatch, capsys)[0] == 0
    assert (root / "pkg" / "use.py").read_bytes() == data.replace(b"client", b"cli2")
    assert (root / "pkg" / "cli2.py").read_bytes() == b"X = 1\n"
