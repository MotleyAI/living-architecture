"""Python `dr-refactor rename-map`: many renames and retargets as one dry-run, one refusal report, one apply."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
import yaml
from project_files import file_tree, write_project
from refactor_cli import assert_same_run, line_col, read, run, template_regex

from living_architecture.contract import message

STORAGE = """\
class StorageBackend:
    def get_model(self, model_name: str) -> int:
        return len(model_name)

    def get_model_sync(self, model_name: str) -> int:
        return self.get_model(model_name=model_name)
"""
STORAGE_USE = """\
from pkg.storage import StorageBackend


def use(s: StorageBackend) -> int:
    return s.get_model(model_name="m") + s.get_model_sync("n")
"""
FILES = {"pkg/storage.py": STORAGE, "pkg/use.py": STORAGE_USE}


def _map(entries: Sequence[Mapping[str, object]]) -> str:
    return yaml.safe_dump(entries, sort_keys=False)


def _rename_map(*flags: str, apply: bool = True, path: str = "map.yaml") -> list[str]:
    return [*(["--apply"] if apply else []), "rename-map", path, *flags]


def _project(tmp_path: Path, files: dict[str, str], entries: Sequence[Mapping[str, object]]) -> Path:
    return write_project(tmp_path / "proj", {**files, "map.yaml": _map(entries)})


def test_related_renames_in_one_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, FILES, [
        {"file": "pkg/storage.py", "symbol": "StorageBackend.get_model", "new_name": "load_model"},
        {"file": "pkg/storage.py", "symbol": "StorageBackend.get_model_sync", "new_name": "load_model_sync"},
        {"file": "pkg/storage.py", "symbol": "StorageBackend.get_model(model_name)", "new_name": "dataset_name"},
    ])
    code, out, err = run(root, _rename_map(), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert out.splitlines()[:3] == [
        "Renaming <get_model> to <load_model>:",
        "Renaming <get_model_sync> to <load_model_sync>:",
        "Renaming <model_name> to <dataset_name>:",
    ]
    assert (out.count("--- a/pkg/storage.py\n"), out.count("--- a/pkg/use.py\n")) == (1, 1)
    assert out.endswith("\n".join([message("refactor.applied", count=2), message("refactor.applied-file", path="pkg/storage.py"),
                                   message("refactor.applied-file", path="pkg/use.py")]) + "\n")
    assert read(root, "pkg/storage.py") == (
        "class StorageBackend:\n"
        "    def load_model(self, dataset_name: str) -> int:\n"
        "        return len(dataset_name)\n\n"
        "    def load_model_sync(self, model_name: str) -> int:\n"
        "        return self.load_model(dataset_name=model_name)\n"
    )
    assert read(root, "pkg/use.py").endswith('    return s.load_model(dataset_name="m") + s.load_model_sync("n")\n')


A = "class A:\n    def old(self, x: int) -> int:\n        return x\n\n\ndef use(a: A) -> int:\n    return a.old(x=1)\n"


def test_entries_name_old_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = _project(tmp_path, {"pkg/a.py": A}, [
        {"file": "pkg/a.py", "symbol": "A.old", "new_name": "new"},
        {"file": "pkg/a.py", "symbol": "A.old(x)", "new_name": "y"},
    ])
    assert run(root, _rename_map(), monkeypatch, capsys)[0] == 0
    assert read(root, "pkg/a.py") == (
        "class A:\n    def new(self, y: int) -> int:\n        return y\n\n\ndef use(a: A) -> int:\n    return a.new(y=1)\n"
    )


TWO_MEMBERS = """\
class Storage:
    def get_model(self) -> int:
        return 1

    def save_model(self) -> None:
        pass
"""


def test_one_combined_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = _project(tmp_path, {
        "pkg/store.py": TWO_MEMBERS,
        "tests/test_b.py": "def test_b(storage):\n    storage.get_model()\n",
        "tests/test_a.py": "def test_a(storage):\n    storage.save_model()\n",
    }, [
        {"file": "pkg/store.py", "symbol": "Storage.get_model", "new_name": "load"},
        {"file": "pkg/store.py", "symbol": "Storage.save_model", "new_name": "store"},
    ])
    before = file_tree(root)
    code, out, err = run(root, _rename_map(), monkeypatch, capsys)
    assert (code, out) == (1, "")
    lines = err.splitlines()
    assert lines[:2] == [
        message("compliance.attr-blindspot", path="tests/test_a.py", line=2, receiver="storage", attr="save_model",
                type="Unknown"),
        message("compliance.attr-blindspot", path="tests/test_b.py", line=2, receiver="storage", attr="get_model",
                type="Unknown"),
    ]
    assert len(lines) == 3
    assert template_regex(message("refactor.blindspots", count=2, attr="ATTR"), attr="ATTR").fullmatch(lines[2])
    assert file_tree(root) == before


def test_duplicate_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = _project(tmp_path, {"pkg/a.py": A}, [
        {"file": "pkg/a.py", "symbol": "A.old", "new_name": "a"},
        {"file": "pkg/a.py", "symbol": "A.old", "new_name": "b"},
    ])
    before = file_tree(root)
    expected = message("refactor.map-duplicate", map="map.yaml", first=1, second=2)
    assert run(root, _rename_map(), monkeypatch, capsys) == (2, "", f"{expected}\n")
    assert file_tree(root) == before


def test_duplicates_are_found_across_locator_kinds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    probe = write_project(tmp_path / "probe", {"pkg/a.py": A})
    _, line, _, col = line_col(probe, "pkg/a.py", "old")
    root = _project(tmp_path, {"pkg/a.py": A}, [
        {"file": "pkg/a.py", "symbol": "A.old", "new_name": "a"},
        {"file": "pkg/a.py", "line": int(line), "col": int(col), "new_name": "b"},
    ])
    expected = message("refactor.map-duplicate", map="map.yaml", first=1, second=2)
    assert run(root, _rename_map(), monkeypatch, capsys) == (2, "", f"{expected}\n")


def test_one_symbol_with_one_intent_merges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    probe = write_project(tmp_path / "probe", {"pkg/a.py": A})
    _, line, _, col = line_col(probe, "pkg/a.py", "old", 1)
    root = _project(tmp_path, {"pkg/a.py": A}, [
        {"file": "pkg/a.py", "symbol": "A.old", "new_name": "new"},
        {"file": "pkg/a.py", "line": int(line), "col": int(col), "new_name": "new"},
    ])
    code, _out, err = run(root, _rename_map(), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/a.py").count("new") == 2


HIERARCHY = """\
class Base:
    def save(self) -> None:
        pass


class Sub(Base):
    def save(self) -> None:
        pass


def use(b: Base) -> None:
    b.save()
"""


def test_conflicting_edits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = _project(tmp_path, {"pkg/h.py": HIERARCHY}, [
        {"file": "pkg/h.py", "symbol": "Base.save", "new_name": "store"},
        {"file": "pkg/h.py", "symbol": "Sub.save", "new_name": "keep"},
    ])
    before = file_tree(root)
    code, out, err = run(root, _rename_map(), monkeypatch, capsys)
    assert (code, out) == (1, "")
    pattern = template_regex(message("refactor.map-conflict", path="PATH", line=999, first=1, second=2),
                             path="PATH", line="999")
    assert pattern.fullmatch(err.rstrip("\n"))
    assert err.startswith("pkg/h.py:")
    assert file_tree(root) == before


PARAMS = "def f(x: int, y: int) -> int:\n    return x - y\n"
NAME_CONFLICT = message("refactor.name-conflict", name="NAME", path="PATH", line=999)


@pytest.mark.parametrize(
    "renames",
    [[("f(x)", "y"), ("f(y)", "x")], [("f(x)", "y"), ("f(y)", "z")]],
    ids=["swap", "chain"],
)
def test_swaps_and_chains_in_one_scope_refuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], renames: list[tuple[str, str]]
) -> None:
    root = _project(tmp_path, {"pkg/f.py": PARAMS},
                    [{"file": "pkg/f.py", "symbol": symbol, "new_name": new} for symbol, new in renames])
    before = file_tree(root)
    code, out, err = run(root, _rename_map(), monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert template_regex(NAME_CONFLICT, name="NAME", path="PATH", line="999").fullmatch(err.rstrip("\n"))
    assert file_tree(root) == before


@pytest.mark.parametrize(
    ("files", "renames", "line"),
    [
        ({"pkg/f.py": PARAMS}, [("f(x)", "z"), ("f(y)", "z")], 1),
        ({"pkg/f.py": "a = 1\nb = 2\n"}, [("a", "x"), ("b", "x")], 1),
    ],
    ids=["parameters", "module names"],
)
def test_two_entries_converging_on_one_name_refuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], files: dict[str, str],
    renames: list[tuple[str, str]], line: int,
) -> None:
    root = _project(tmp_path, files, [{"file": "pkg/f.py", "symbol": symbol, "new_name": new} for symbol, new in renames])
    before = file_tree(root)
    code, out, err = run(root, _rename_map(), monkeypatch, capsys)
    new = renames[0][1]
    assert (code, out, err) == (1, "", message("refactor.name-conflict", name=new, path="pkg/f.py", line=line) + "\n")
    assert file_tree(root) == before


def test_mixed_languages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = _project(tmp_path, {"pkg/a.py": A, "web/a.ts": "export function old(): number { return 1; }\n"}, [
        {"file": "pkg/a.py", "symbol": "A.old", "new_name": "new"},
        {"file": "web/a.ts", "symbol": "old", "new_name": "next"},
    ])
    before = file_tree(root)
    expected = message("refactor.map-mixed-languages", map="map.yaml", languages="python, typescript")
    assert run(root, _rename_map(), monkeypatch, capsys) == (2, "", f"{expected}\n")
    assert file_tree(root) == before


@pytest.mark.parametrize(
    ("second", "index"),
    [
        ({"file": "pkg/a.py", "symbol": "A.old", "new_name": "new", "retarget": "A.new"}, 2),
        ({"file": "pkg/a.py", "symbol": "A.old", "line": 2, "new_name": "new"}, 2),
        ({"symbol": "A.old", "new_name": "new"}, 2),
    ],
    ids=["both-intents", "two-locators", "no-file"],
)
def test_invalid_map(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    second: dict[str, object],
    index: int,
) -> None:
    root = _project(tmp_path, {"pkg/a.py": A}, [{"file": "pkg/a.py", "symbol": "A.old(x)", "new_name": "y"}, second])
    before = file_tree(root)
    expected = message("refactor.map-invalid", map="map.yaml", index=index)
    assert run(root, _rename_map(), monkeypatch, capsys) == (2, "", f"{expected}\n")
    assert file_tree(root) == before


@pytest.mark.parametrize("apply", [False, True], ids=["dry-run", "apply"])
def test_single_rename_equals_its_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], apply: bool
) -> None:
    entry = [{"file": "pkg/storage.py", "symbol": "StorageBackend.get_model", "new_name": "load_model"}]
    flags = ["--apply"] if apply else []
    reference = [*flags, "rename", "--file", "pkg/storage.py", "--symbol", "StorageBackend.get_model", "--new-name",
                 "load_model"]
    left = write_project(tmp_path / "left", FILES)
    right = write_project(tmp_path / "right", {**FILES, "map.yaml": _map(entry)})
    expected = run(left, reference, monkeypatch, capsys)
    assert expected[0] == 0, expected
    assert run(right, _rename_map(apply=apply), monkeypatch, capsys) == expected
    (right / "map.yaml").unlink()
    assert file_tree(right) == file_tree(left)


ENGINE = """\
class Engine:
    def save_model(self, m: int) -> None:
        print(m)

    def save(self, m: int) -> None:
        return self.save_model(m)
"""
ENGINE_USE = "from pkg.engine import Engine\n\n\ndef use(engine: Engine) -> None:\n    engine.save(1)\n"


def test_single_retarget_equals_its_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"pkg/engine.py": ENGINE, "pkg/use.py": ENGINE_USE}
    entry = [{"file": "pkg/engine.py", "symbol": "Engine.save", "retarget": "Engine.save_model"}]
    assert_same_run(
        tmp_path, files,
        ["--apply", "retarget", "--file", "pkg/engine.py", "--symbol", "Engine.save", "--target", "Engine.save_model"],
        _rename_map(), monkeypatch, capsys, extra={"map.yaml": _map(entry)},
    )


def test_map_headers_follow_entry_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {"pkg/engine.py": ENGINE, "pkg/use.py": ENGINE_USE}, [
        {"file": "pkg/engine.py", "symbol": "Engine.save_model(m)", "new_name": "model"},
        {"file": "pkg/engine.py", "symbol": "Engine.save", "retarget": "Engine.save_model"},
    ])
    code, out, _err = run(root, _rename_map(apply=False), monkeypatch, capsys)
    assert code == 0
    assert out.splitlines()[:2] == [
        "Renaming <m> to <model>:",
        message("refactor.retarget-header", old="save", new="save_model"),
    ]


def test_retarget_follows_a_renamed_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {"pkg/engine.py": ENGINE, "pkg/use.py": ENGINE_USE}, [
        {"file": "pkg/engine.py", "symbol": "Engine.save_model", "new_name": "persist"},
        {"file": "pkg/engine.py", "symbol": "Engine.save", "retarget": "Engine.save_model"},
    ])
    code, _out, err = run(root, _rename_map(), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert read(root, "pkg/engine.py") == ENGINE.replace("save_model", "persist")
    assert read(root, "pkg/use.py") == ENGINE_USE.replace("engine.save(1)", "engine.persist(1)")


def test_entry_files_are_relative_to_the_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = write_project(tmp_path / "proj", {"pkg/a.py": A})
    (tmp_path / "maps").mkdir()
    (tmp_path / "maps" / "m.yaml").write_text(_map([{"file": "pkg/a.py", "symbol": "A.old", "new_name": "new"}]),
                                              encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    code, out, err = run(tmp_path, ["--project", "proj", *_rename_map(path="maps/m.yaml")], monkeypatch, capsys)
    assert (code, err) == (0, ""), out
    assert "a.new(x=1)" in read(root, "pkg/a.py")


@pytest.mark.skipif(not hasattr(os, "geteuid") or os.geteuid() == 0, reason="needs a non-root user to deny a write")
def test_failed_write_rolls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    files = {
        "pkg/a.py": "def old() -> int:\n    return 1\n",
        "pkg/b.py": "from pkg.a import old\n\nX = old()\n",
        "pkg/zz/__init__.py": "",
        "pkg/zz/c.py": "from pkg.a import old\n\nY = old()\n",
    }
    root = _project(tmp_path, files, [{"file": "pkg/a.py", "symbol": "old", "new_name": "new"}])
    before = file_tree(root)
    locked = root / "pkg" / "zz"
    locked.chmod(0o555)
    try:
        code, out, err = run(root, _rename_map(), monkeypatch, capsys)
    finally:
        locked.chmod(0o755)
    assert code == 1
    assert err == f"{message('refactor.write-failed', path='pkg/zz/c.py')}\n"
    assert message("refactor.applied", count=3).strip() not in out
    assert file_tree(root) == before


PATCHED = """\
from unittest.mock import patch


def test_patched() -> None:
    with patch("pkg.engine.Engine.save_model"):
        pass
"""


def test_a_later_entry_renaming_a_target_segment_rewrites_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {"pkg/engine.py": ENGINE, "tests/test_p.py": PATCHED}, [
        {"file": "pkg/engine.py", "symbol": "Engine.save_model", "new_name": "store_model"},
        {"file": "pkg/engine.py", "symbol": "Engine", "new_name": "Motor"},
    ])
    code, _out, err = run(root, _rename_map(), monkeypatch, capsys)
    assert (code, err) == (0, "")
    assert 'patch("pkg.engine.Motor.store_model")' in read(root, "tests/test_p.py")


SHARED_OLD = """\
class A:
    def save(self) -> int:
        return 1


class B:
    def save(self) -> int:
        return 2


def use(x):
    return x.save()
"""


def test_entries_sharing_an_old_name_report_each_blind_spot_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {"pkg/m.py": SHARED_OLD}, [
        {"file": "pkg/m.py", "symbol": "A.save", "new_name": "store"},
        {"file": "pkg/m.py", "symbol": "B.save", "new_name": "keep"},
    ])
    code, _out, err = run(root, _rename_map(), monkeypatch, capsys)
    blind = message("compliance.attr-blindspot", path="pkg/m.py", line=12, receiver="x", attr="save", type="Unknown")
    assert (code, err) == (1, f"{blind}\n{message('refactor.blindspots', count=1, attr='save')}\n")
