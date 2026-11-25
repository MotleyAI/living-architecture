"""Python member renames refuse a new name the class's namespace holds, as the checker's class graph has it."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from project_files import write_project
from refactor_cli import entry_refusal, run
from trmv.contract import message

EXTLIB = (
    "class Root:\n    def keys(self) -> int:\n        return 0\n\n\n"
    "class Mid(Root):\n    pass\n"
)


def _venv(root: Path) -> Path:
    """A virtualenv layout holding one installed package, `extlib`, that la's own environment lacks."""
    site = root / "lib" / "python3.12" / "site-packages" / "extlib"
    site.mkdir(parents=True)
    (site / "__init__.py").write_text(EXTLIB, encoding="utf-8")
    (root / "pyvenv.cfg").write_text("home = /usr/bin\nversion = 3.12.0\n", encoding="utf-8")
    return root


@pytest.mark.parametrize("new", ["keys", "\uff4b\uff45\uff59\uff53"], ids=["ascii", "full-width"])
@pytest.mark.parametrize("base", ["Root", "Mid"], ids=["direct", "transitive"])
def test_a_member_renamed_onto_a_name_a_library_base_declares(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], base: str, new: str
) -> None:
    venv = _venv(tmp_path / "venvs" / "v")
    root = write_project(tmp_path / "proj", {
        "pyrightconfig.json": json.dumps({"venvPath": str(venv.parent), "venv": venv.name}) + "\n",
        "pkg/m.py": f"from extlib import {base}\n\n\nclass C({base}):\n    def old(self) -> int:\n        return 1\n",
    }, venv=False)
    argv = ["rename", "--file", "pkg/m.py", "--symbol", "C.old", "--new-name", new]
    conflict = entry_refusal("pkg/m.py C.old", message("refactor.name-conflict", name=new, path="pkg/m.py", line=5))
    assert run(root, argv, monkeypatch, capsys) == (1, "", conflict + "\n")


def test_a_member_renamed_onto_a_name_a_project_ancestor_declares_through_a_cast_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # rope evaluates the cast to a builtin object; the checker to Root.
    root = write_project(tmp_path / "proj", {
        "pkg/root.py": "class Root:\n    def new(self) -> int:\n        return 0\n",
        "pkg/m.py": (
            "from typing import cast\n\nfrom pkg.root import Root\n\n\n"
            'class C(cast("type[Root]", object)):\n    def old(self) -> int:\n        return 1\n'
        ),
    })
    argv = ["rename", "--file", "pkg/m.py", "--symbol", "C.old", "--new-name", "new"]
    conflict = entry_refusal("pkg/m.py C.old", message("refactor.name-conflict", name="new", path="pkg/root.py", line=2))
    assert run(root, argv, monkeypatch, capsys) == (1, "", conflict + "\n")
