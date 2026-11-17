"""A Python rename refuses a new name that is not an identifier, and `--stub` refuses a config it cannot read."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from project_files import write_project
from refactor_cli import run, run_raw

from living_architecture.config import ConfigError, load_config
from living_architecture.contract import language, message

FILES = {"pkg/a.py": "def foo() -> int:\n    return 1\n", "pkg/use.py": "from pkg import a\n\nprint(a.foo())\n"}


@pytest.mark.parametrize("new", ["bad-name", "class", "\uff43\uff4c\uff41\uff53\uff53"], ids=["hyphen", "keyword", "full-width-keyword"])
@pytest.mark.parametrize("locator", [["--symbol", "foo"], []], ids=["symbol", "module"])
def test_a_new_name_that_is_not_an_identifier_cannot_be_renamed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], new: str, locator: list[str]
) -> None:
    root = write_project(tmp_path / "proj", FILES)
    code, out, err = run_raw(root, ["--apply", "rename", "--file", "pkg/a.py", *locator, "--new-name", new], monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert err.endswith(message("refactor.cannot-rename") + "\n")
    assert sorted(p.name for p in (root / "pkg").iterdir()) == ["__init__.py", "a.py", "use.py"]
    assert (root / "pkg" / "a.py").read_text(encoding="utf-8") == FILES["pkg/a.py"]


def test_a_module_moves_to_the_normal_form_of_its_new_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {**FILES, "pkg/__init__.py": 'from . import a\n\n__all__ = ["a"]\n'})
    wide = "\uff42"  # full-width b, NFKC "b"
    code, _out, err = run(root, ["--apply", "rename", "--file", "pkg/a.py", "--new-name", wide], monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert sorted(p.name for p in (root / "pkg").iterdir()) == ["__init__.py", "b.py", "use.py"]
    assert (root / "pkg" / "__init__.py").read_text(encoding="utf-8") == f'from . import {wide}\n\n__all__ = ["b"]\n'
    assert (root / "pkg" / "use.py").read_text(encoding="utf-8") == f"from pkg import {wide}\n\nprint({wide}.foo())\n"


@pytest.mark.parametrize("locator", [["--symbol", "foo"], []], ids=["symbol", "module"])
def test_a_rename_to_the_same_name_refuses_a_line_keep_it_leaves_unmatched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], locator: list[str]
) -> None:
    root = write_project(tmp_path / "proj", FILES)
    same = "foo" if locator else "a"
    argv = ["rename", "--file", "pkg/a.py", *locator, "--new-name", same, "--keep", "pkg/use.py:3"]
    unmatched = message("refactor.keep-unmatched", site="pkg/use.py:3")
    assert run(root, argv, monkeypatch, capsys) == (2, "", unmatched + "\n")


@pytest.mark.parametrize("same", ["a", "\uff41"], ids=["as-written", "full-width"])
def test_a_module_renamed_to_its_own_name_is_a_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], same: str
) -> None:
    root = write_project(tmp_path / "proj", {**FILES, "pkg/old.py": "# coding: nosuch\nfrom pkg import a\n"})
    code, _out, err = run(root, ["rename", "--file", "pkg/a.py", "--new-name", same], monkeypatch, capsys)
    assert (code, err) == (0, "")


@pytest.mark.parametrize("baseline", [False, True], ids=["no-baseline", "baseline"])
def test_a_stub_with_an_unreadable_config_is_refused_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], baseline: bool
) -> None:
    root = write_project(tmp_path / "proj", {**FILES, "living-architecture.yaml": "format: [\n"})
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    if baseline:
        path = root / language("python")["baseline_file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ConfigError) as error:
        load_config(root)
    argv = ["rename", "--file", "pkg/a.py", "--new-name", "b", "--stub", "2.0"]
    assert run(root, argv, monkeypatch, capsys) == (2, "", str(error.value) + "\n")
