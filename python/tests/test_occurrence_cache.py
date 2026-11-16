"""The occurrence index's whole-run cache: reused exactly when nothing that can change the index changed, kept
outside the project, and never changing the output."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from project_files import file_tree, write_project
from refactor_cli import run_raw

from living_architecture.cli.dr_compliance import dr_compliance
from living_architecture.contract import language
from living_architecture.lang import LanguageServer

MODELS = """class Store:
    def get_model(self) -> int:
        return 1


class Unrelated:
    def get_model(self) -> int:
        return 2
"""
USE = """import extpkg

from pkg.lib import value
from pkg.models import Store


def f(s: Store) -> int:
    return s.get_model() + extpkg.helper() + value
"""
STAND_IN = "pkg/models.py:7"
RENAME = ["rename", "--file", "pkg/models.py", "--symbol", "Store.get_model", "--new-name", "load_model"]
CLEAN = [*RENAME, "--without", STAND_IN]


class Exports:
    """The occurrence exports a run asks for (the startup self-test aside) and the servers it starts."""

    def __init__(self) -> None:
        self.count = 0
        self.starts = 0

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        export, enter = LanguageServer.export, LanguageServer.__enter__

        def counting(server: LanguageServer, request: Any) -> Any:
            self.count += bool(request.names)
            return export(server, request)

        def starting(server: LanguageServer) -> LanguageServer:
            self.starts += 1
            return enter(server)

        monkeypatch.setattr(LanguageServer, "export", counting)
        monkeypatch.setattr(LanguageServer, "__enter__", starting)


def _venv(root: Path, minor: int = 12) -> Path:
    """A virtualenv layout holding one installed package, `extpkg`."""
    site = root / "lib" / f"python3.{minor}" / "site-packages" / "extpkg"
    site.mkdir(parents=True)
    (site / "__init__.py").write_text("def helper() -> int:\n    return 1\n", encoding="utf-8")
    (root / "pyvenv.cfg").write_text(f"home = /usr/bin\nversion = 3.{minor}.0\n", encoding="utf-8")
    return root


def _config(venv: Path, **extra: str) -> str:
    return json.dumps({"venvPath": str(venv.parent), "venv": venv.name, **extra}) + "\n"


@pytest.fixture
def venv(tmp_path: Path) -> Path:
    return _venv(tmp_path / "venvs" / "v")


@pytest.fixture
def project(tmp_path: Path, venv: Path) -> Path:
    return write_project(tmp_path / "proj", {
        "pyrightconfig.json": _config(venv),
        "pkg/models.py": MODELS,
        "pkg/use.py": USE,
        "pkg/lib.py": "value = 1\n",
        "pkg/extra.py": "y = 2\n",
    }, venv=False)


def _run(root: Path, argv: list[str], monkeypatch: pytest.MonkeyPatch,
         capsys: pytest.CaptureFixture[str]) -> tuple[Exports, tuple[int, str, str]]:
    exports = Exports()
    with monkeypatch.context() as patched:
        exports.install(patched)
        result = run_raw(root, argv, patched, capsys)
    return exports, result


def _uncached(tmp_path: Path, root: Path, argv: list[str], monkeypatch: pytest.MonkeyPatch,
              capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    """`argv` on `root` with an empty cache of its own."""
    with monkeypatch.context() as patched:
        patched.setenv("LA_CACHE_DIR", str(tmp_path / "fresh-cache"))
        return run_raw(root, argv, patched, capsys)


def _cache_files(cache_dir: Path) -> list[Path]:
    return sorted(p for p in cache_dir.rglob("*") if p.is_file())


def test_rerun_with_only_classification_flags_added_exports_nothing(
    tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first, (code, _out, _err) = _run(project, RENAME, monkeypatch, capsys)
    assert (code, first.count) == (1, 1)
    second, result = _run(project, CLEAN, monkeypatch, capsys)
    assert (second.count, second.starts) == (0, 0)
    assert result[0] == 0
    assert result == _uncached(tmp_path, project, CLEAN, monkeypatch, capsys)


def _edit_source(root: Path, venv: Path) -> None:
    (root / "pkg" / "extra.py").write_text("y = 3\n", encoding="utf-8")


def _shadow_an_import(root: Path, venv: Path) -> None:
    (root / "pkg" / "lib").mkdir()
    (root / "pkg" / "lib" / "__init__.py").write_text('value = "s"\n', encoding="utf-8")


def _delete_a_file(root: Path, venv: Path) -> None:
    (root / "pkg" / "extra.py").unlink()


def _change_the_checker_config(root: Path, venv: Path) -> None:
    (root / "pyrightconfig.json").write_text(_config(venv, reportMissingImports="none"), encoding="utf-8")


def _change_an_installed_package(root: Path, venv: Path) -> None:
    init = venv / "lib" / "python3.12" / "site-packages" / "extpkg" / "__init__.py"
    init.write_text("def helper() -> str:\n    return 'x'\n", encoding="utf-8")


def _change_the_interpreter(root: Path, venv: Path) -> None:
    (venv / "lib" / "python3.12").rename(venv / "lib" / "python3.13")
    (venv / "pyvenv.cfg").write_text("home = /usr/bin\nversion = 3.13.0\n", encoding="utf-8")


@pytest.mark.parametrize(
    "change",
    [_edit_source, _shadow_an_import, _delete_a_file, _change_the_checker_config, _change_an_installed_package,
     _change_the_interpreter],
    ids=["source-edit", "shadowing-module", "deleted-file", "checker-config", "installed-package", "interpreter"],
)
def test_a_change_the_index_depends_on_exports_anew(
    tmp_path: Path, project: Path, venv: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    change: Callable[[Path, Path], None],
) -> None:
    first, _ = _run(project, CLEAN, monkeypatch, capsys)
    assert first.count == 1
    change(project, venv)
    second, result = _run(project, CLEAN, monkeypatch, capsys)
    assert second.count == 1
    assert result == _uncached(tmp_path, project, CLEAN, monkeypatch, capsys)


def _change_the_extended_config(base: Path, venv: Path) -> None:
    base.write_text(_config(venv, reportMissingImports="none"), encoding="utf-8")


def _change_a_package_of_the_extended_venv(base: Path, venv: Path) -> None:
    _change_an_installed_package(base, venv)


@pytest.mark.parametrize("change", [_change_the_extended_config, _change_a_package_of_the_extended_venv],
                         ids=["extended-config", "extended-venv"])
def test_a_change_through_an_extended_config_exports_anew(
    tmp_path: Path, project: Path, venv: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    change: Callable[[Path, Path], None],
) -> None:
    base = tmp_path / "shared" / "base.json"
    base.parent.mkdir()
    base.write_text(_config(venv), encoding="utf-8")
    (project / "pyrightconfig.json").write_text(json.dumps({"extends": "../shared/base.json"}), encoding="utf-8")
    first, _ = _run(project, CLEAN, monkeypatch, capsys)
    assert first.count == 1
    change(base, venv)
    second, result = _run(project, CLEAN, monkeypatch, capsys)
    assert second.count == 1
    assert result == _uncached(tmp_path, project, CLEAN, monkeypatch, capsys)


def test_a_source_changed_during_the_export_is_not_cached(
    project: Path, cache_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    export = LanguageServer.export

    def editing(server: LanguageServer, request: Any) -> Any:
        found = export(server, request)
        if request.names:
            (project / "pkg" / "extra.py").write_text("y = 3\n", encoding="utf-8")
        return found

    with monkeypatch.context() as patched:
        patched.setattr(LanguageServer, "export", editing)
        run_raw(project, CLEAN, patched, capsys)
    assert _cache_files(cache_dir) == []


def test_a_cache_directory_inside_the_project_is_no_cache(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LA_CACHE_DIR", str(project / ".cache" / "la"))
    before = file_tree(project)
    first, _ = _run(project, CLEAN, monkeypatch, capsys)
    second, _ = _run(project, CLEAN, monkeypatch, capsys)
    assert (first.count, second.count) == (1, 1)
    assert file_tree(project) == before


def test_a_changed_request_exports_anew(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(project, CLEAN, monkeypatch, capsys)
    second, (code, _out, _err) = _run(
        project, ["rename", "--file", "pkg/models.py", "--symbol", "Store", "--new-name", "Depot"], monkeypatch, capsys)
    assert (code, second.count) == (0, 1)


@pytest.mark.parametrize("damage", ["truncate", "garbage"])
def test_a_damaged_cache_entry_is_a_miss_with_the_same_output(
    project: Path, cache_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], damage: str
) -> None:
    _, expected = _run(project, CLEAN, monkeypatch, capsys)
    entries = _cache_files(cache_dir)
    assert entries
    for entry in entries:
        if damage == "truncate":
            entry.write_bytes(entry.read_bytes()[: max(1, entry.stat().st_size // 2)])
        else:
            entry.write_bytes(b"\x00not a cache entry\xff")
    second, result = _run(project, CLEAN, monkeypatch, capsys)
    assert second.count == 1
    assert result == expected


def test_one_entry_per_project_root(
    tmp_path: Path, project: Path, venv: Path, cache_dir: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str]
) -> None:
    _run(project, CLEAN, monkeypatch, capsys)
    one = len(_cache_files(cache_dir))
    _run(project, ["rename", "--file", "pkg/models.py", "--symbol", "Store", "--new-name", "Depot"], monkeypatch, capsys)
    assert len(_cache_files(cache_dir)) == one
    other = write_project(tmp_path / "other", {"pyrightconfig.json": _config(venv), "pkg/models.py": MODELS,
                                               "pkg/use.py": USE, "pkg/lib.py": "value = 1\n"}, venv=False)
    _run(other, CLEAN, monkeypatch, capsys)
    assert len(_cache_files(cache_dir)) == 2 * one


@pytest.mark.parametrize("apply", [False, True], ids=["dry-run", "apply"])
def test_no_cache_file_is_written_in_the_project(
    project: Path, cache_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], apply: bool
) -> None:
    before = file_tree(project)
    _run(project, [*(["--apply"] if apply else []), *CLEAN], monkeypatch, capsys)
    after = file_tree(project)
    assert after.keys() - before.keys() == set()
    changed = {p for p in before.keys() & after.keys() if before[p] != after[p]}
    assert changed == ({"pkg/models.py", "pkg/use.py"} if apply else set())
    assert _cache_files(cache_dir)


@pytest.mark.skipif(sys.platform == "win32", reason="the XDG cache directory is POSIX")
def test_without_la_cache_dir_the_cache_is_in_the_user_cache_directory(
    tmp_path: Path, project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("LA_CACHE_DIR")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    first, _ = _run(project, CLEAN, monkeypatch, capsys)
    second, _ = _run(project, CLEAN, monkeypatch, capsys)
    assert (first.count, second.count) == (1, 0)
    assert _cache_files(tmp_path / "xdg" / "living-architecture")


def test_the_cache_variable_is_declared_in_the_shared_contract() -> None:
    assert language("python")["cache_dir_variable"] == "LA_CACHE_DIR"
    assert os.environ["LA_CACHE_DIR"]


UNTYPED_USE = "def g(m):\n    return m.get_model()\n"


def test_attr_reuses_its_index_until_a_source_changes(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (project / "pkg" / "untyped.py").write_text(UNTYPED_USE, encoding="utf-8")
    monkeypatch.chdir(project)
    argv = ["--select", "attr-blindspot", "--attr", "get_model", "pkg"]
    outputs = []
    for edit in (False, False, True):
        if edit:
            (project / "pkg" / "extra.py").write_text("y = 3\n", encoding="utf-8")
        exports = Exports()
        with monkeypatch.context() as patched:
            exports.install(patched)
            code = dr_compliance(argv)
        outputs.append((code, capsys.readouterr(), exports.count))
    assert [count for *_, count in outputs] == [1, 0, 1]
    assert outputs[0][:2] == outputs[1][:2] == outputs[2][:2]
    assert outputs[0][0] == 1
