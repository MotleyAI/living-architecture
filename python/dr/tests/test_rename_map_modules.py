"""Python `dr-refactor rename-map` with module entries: one union with every other entry, one check, one write."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
import yaml

from deterministic_refactor.config import current_format
from deterministic_refactor.contract import message
from deterministic_refactor.lang import LanguageServer
from project_files import file_tree, write_project
from refactor_cli import entry_refusal, read, run, run_raw, template_regex

CHECKS = "[resolve]\n[checks]\n"
Entries = Sequence[Mapping[str, object]]


def _project(tmp_path: Path, files: dict[str, str], entries: Entries) -> Path:
    return write_project(tmp_path / "proj", {**files, "map.yaml": yaml.safe_dump(list(entries), sort_keys=False)})


def _map(*flags: str, apply: bool = True) -> list[str]:
    return [*(["--apply"] if apply else []), "rename-map", "map.yaml", *flags]


def _offset(text: str, before: str) -> int:
    """The offset just after `before` in `text`."""
    return text.index(before) + len(before)


def _conflict(name: str, path: str, line: int) -> str:
    return message("refactor.name-conflict", name=name, path=path, line=line)


def _under(root: Path, prefix: str) -> dict[str, bytes]:
    return {rel: data for rel, data in file_tree(root).items() if rel.startswith(prefix)}


# ---- the map file and routing


def test_module_entries_are_loaded_and_computed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {"pkg/a.py": "X = 1\n", "pkg/use.py": "from pkg import a\n\nprint(a.X)\n"},
                    [{"module": "pkg/a.py", "new_name": "b"}])
    code, out, err = run(root, _map(), monkeypatch, capsys)
    assert (code, err) == (0, ""), err
    assert out.startswith("Renaming <a> to <b>:\n")
    assert "rename from pkg/a.py\nrename to pkg/b.py\n" in out
    assert read(root, "pkg/b.py") == "X = 1\n"
    assert read(root, "pkg/use.py") == "from pkg import b\n\nprint(b.X)\n"


def test_invalid_module_entries_are_named_in_index_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {"pkg/a.py": "def f() -> None:\n    pass\n"}, [
        {"module": "pkg/a.py", "symbol": "f", "new_name": "b"},
        {"module": "pkg/a.py", "retarget": "f"},
        {"module": "pkg/a.py", "file": "pkg/a.py", "new_name": "b"},
        {"module": "pkg/a.py", "new_name": "b"},
        {"module": "pkg/a.py"},
    ])
    before = file_tree(root)
    expected = "".join(message("refactor.map-invalid", map="map.yaml", index=i) + "\n" for i in (1, 2, 3, 5))
    assert run_raw(root, _map(), monkeypatch, capsys) == (2, "", expected)
    assert file_tree(root) == before


@pytest.mark.parametrize("args", [
    ["--apply", "rename", "--file", "__init__.py", "--new-name", "foo"],
    _map(),
])
def test_the_project_roots_init_names_no_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], args: list[str]
) -> None:
    root = _project(tmp_path, {"__init__.py": "X = 1\n", "a.py": "import os\n"},
                    [{"module": "__init__.py", "new_name": "foo"}, {"module": "a.py", "new_name": "b"}])
    before = file_tree(root)
    refused = entry_refusal("__init__.py", message("refactor.cannot-rename"))
    assert run_raw(root, args, monkeypatch, capsys) == (1, "", CHECKS + refused + "\n")
    assert file_tree(root) == before


def test_a_module_entry_of_another_language_mixes_the_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {"pkg/a.py": "def f() -> None:\n    pass\n", "web/b.ts": "export {};\n"},
                    [{"file": "pkg/a.py", "symbol": "f", "new_name": "g"}, {"module": "web/b.ts", "new_name": "c"}])
    finding = message("refactor.map-mixed-languages", map="map.yaml", languages="python, typescript")
    assert run_raw(root, _map(), monkeypatch, capsys) == (2, "", finding + "\n")


@pytest.mark.parametrize(("module", "finding"), [
    ("notes.txt", "refactor.unsupported-extension"),
    ("pkg/gone.py", "refactor.source-missing"),
    ("pkg/sql", "refactor.source-missing"),
    ("../outside.py", "refactor.outside-project"),
], ids=["unsupported", "missing", "directory", "outside"])
def test_a_module_entry_routes_by_its_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], module: str, finding: str
) -> None:
    files = {"pkg/a.py": "def f() -> None:\n    pass\n", "pkg/sql/__init__.py": "", "notes.txt": "a\n"}
    (tmp_path / "outside.py").write_text("X = 1\n", encoding="utf-8")
    root = _project(tmp_path, files, [{"file": "pkg/a.py", "symbol": "f", "new_name": "g"},
                                      {"module": module, "new_name": "c"}])
    expected = message(finding, path=str(root / module))
    assert run_raw(root, _map(), monkeypatch, capsys) == (1, "", expected + "\n")


# ---- module entries beside other entries

JOIN_USE = "from pkg.join_edges import JoinEdge\n\n\ndef load() -> JoinEdge:\n    return JoinEdge()\n"


def test_a_module_entry_beside_symbol_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {"pkg/join_edges.py": "class JoinEdge:\n    pass\n", "pkg/use.py": JOIN_USE}, [
        {"module": "pkg/join_edges.py", "new_name": "relationship_edges"},
        {"file": "pkg/join_edges.py", "symbol": "JoinEdge", "new_name": "RelationshipEdge"},
        {"file": "pkg/use.py", "symbol": "load", "new_name": "read"},
    ])
    code, out, err = run(root, _map(), monkeypatch, capsys)
    assert (code, err) == (0, ""), err
    assert out.splitlines()[:3] == [
        "Renaming <join_edges> to <relationship_edges>:",
        "Renaming <JoinEdge> to <RelationshipEdge>:",
        "Renaming <load> to <read>:",
    ]
    order = [out.index("--- a/pkg/join_edges.py\n"), out.index("rename from pkg/join_edges.py\nrename to pkg/relationship_edges.py\n"),
             out.index("--- a/pkg/use.py\n")]
    assert order == sorted(order)
    assert "--- a/pkg/relationship_edges.py\n" not in out
    assert not (root / "pkg" / "join_edges.py").exists()
    assert read(root, "pkg/relationship_edges.py") == "class RelationshipEdge:\n    pass\n"
    assert read(root, "pkg/use.py") == (
        "from pkg.relationship_edges import RelationshipEdge\n\n\ndef read() -> RelationshipEdge:\n    return RelationshipEdge()\n"
    )


IMPORT_USE = "import pkg.a\n\n\ndef load() -> int:\n    return pkg.a.X\n"


def test_a_module_entry_located_on_an_import(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {"pkg/a.py": "X = 1\n", "pkg/use.py": IMPORT_USE}, [
        {"file": "pkg/use.py", "symbol": "load", "new_name": "read"},
        {"file": "pkg/use.py", "offset": _offset(IMPORT_USE, "import pkg."), "new_name": "b"},
    ])
    code, _out, err = run(root, _map(), monkeypatch, capsys)
    assert (code, err) == (0, ""), err
    assert read(root, "pkg/b.py") == "X = 1\n"
    assert read(root, "pkg/use.py") == "import pkg.b\n\n\ndef read() -> int:\n    return pkg.b.X\n"


# ---- one module identity

IDENTITIES = {
    "module": ({"pkg/a.py": "X = 1\n"}, "pkg/a.py", "pkg.a", "pkg/a.py"),
    "package": ({"pkg/sql/__init__.py": "X = 1\n"}, "pkg/sql/__init__.py", "pkg.sql", "pkg/sql"),
    "namespace-member": ({"ns/client.py": "X = 1\n"}, "ns/client.py", "ns.client", "ns/client.py"),
}


@pytest.mark.parametrize("kind", list(IDENTITIES))
def test_a_path_entry_and_an_import_entry_of_one_module_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], kind: str
) -> None:
    files, module, dotted, moved = IDENTITIES[kind]
    use = f"import {dotted}\n\nprint({dotted}.X)\n"
    root = _project(tmp_path, {**files, "use.py": use}, [
        {"module": module, "new_name": "fresh"},
        {"file": "use.py", "offset": _offset(use, "import " + dotted.rpartition(".")[0] + "."), "new_name": "fresh"},
    ])
    code, out, err = run(root, _map(), monkeypatch, capsys)
    assert (code, err) == (0, ""), err
    assert out.count(f"rename from {moved}\n") == 1
    renamed = dotted.rpartition(".")[0] + ".fresh"
    assert read(root, "use.py") == f"import {renamed}\n\nprint({renamed}.X)\n"


@pytest.mark.parametrize("kind", list(IDENTITIES))
def test_a_path_entry_and_an_import_entry_of_one_module_with_different_names_are_duplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], kind: str
) -> None:
    files, module, dotted, _moved = IDENTITIES[kind]
    use = f"import {dotted}\n\nprint({dotted}.X)\n"
    root = _project(tmp_path, {**files, "use.py": use}, [
        {"module": module, "new_name": "b"},
        {"file": "use.py", "offset": _offset(use, "import " + dotted.rpartition(".")[0] + "."), "new_name": "c"},
    ])
    before = file_tree(root)
    code, out, err = run(root, _map(), monkeypatch, capsys)
    assert (code, out) == (2, "")
    assert err.endswith(message("refactor.map-duplicate", map="map.yaml", first=1, second=2) + "\n")
    assert file_tree(root) == before


# ---- nested moves compose

NESTED = {"pkg/sql/__init__.py": "", "pkg/sql/client.py": "X = 1\n",
          "app.py": "import pkg.sql.client\n\nprint(pkg.sql.client.X)\n"}
PACKAGE = {"module": "pkg/sql/__init__.py", "new_name": "db"}
CLIENT = {"module": "pkg/sql/client.py", "new_name": "cli"}


@pytest.mark.parametrize("entries", [[PACKAGE, CLIENT], [CLIENT, PACKAGE]], ids=["package-first", "module-first"])
def test_a_package_and_a_module_inside_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], entries: Entries
) -> None:
    root = _project(tmp_path, NESTED, entries)
    code, out, err = run(root, _map(), monkeypatch, capsys)
    assert (code, err) == (0, ""), err
    assert "rename from pkg/sql\nrename to pkg/db\n" in out
    assert "rename from pkg/sql/client.py\nrename to pkg/sql/cli.py\n" in out
    assert not (root / "pkg" / "sql").exists()
    assert sorted(_under(root, "pkg/db/")) == ["pkg/db/__init__.py", "pkg/db/cli.py"]
    assert read(root, "pkg/db/cli.py") == "X = 1\n"
    assert read(root, "app.py") == "import pkg.db.cli\n\nprint(pkg.db.cli.X)\n"


THREE = {"pkg/sql/__init__.py": "", "pkg/sql/client.py": "X = 1\n", "main.py": "from pkg.sql import client\n\nprint(client.X)\n"}
OUTER = {"module": "pkg/__init__.py", "new_name": "app"}


@pytest.mark.parametrize("entries", [[OUTER, PACKAGE, CLIENT], [CLIENT, PACKAGE, OUTER], [PACKAGE, OUTER, CLIENT]],
                         ids=["outermost-first", "innermost-first", "middle-first"])
def test_three_nested_moves_compose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], entries: Entries
) -> None:
    root = _project(tmp_path, THREE, entries)
    code, _out, err = run(root, _map(), monkeypatch, capsys)
    assert (code, err) == (0, ""), err
    assert not (root / "pkg").exists()
    assert sorted(_under(root, "app/")) == ["app/__init__.py", "app/db/__init__.py", "app/db/cli.py"]
    assert read(root, "main.py") == "from app.db import cli\n\nprint(cli.X)\n"


@pytest.mark.parametrize("apply", [False, True], ids=["dry-run", "apply"])
def test_three_nested_moves_print_each_entrys_own_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], apply: bool
) -> None:
    root = _project(tmp_path, THREE, [CLIENT, OUTER, PACKAGE])
    code, out, _err = run(root, _map(apply=apply), monkeypatch, capsys)
    assert code == 0
    pairs = [line for line in out.splitlines() if line.startswith("rename ")]
    assert pairs == ["rename from pkg", "rename to app", "rename from pkg/sql", "rename to pkg/db",
                     "rename from pkg/sql/client.py", "rename to pkg/sql/cli.py"]


def _refused_with_a_conflict_on(name: str, err: str, locator: str, entry: int) -> bool:
    """The last line of `err` is `entry`'s conflict on `name`, at any site."""
    refused = entry_refusal(locator, _conflict(name, "PATH", 999), entry)
    return template_regex(refused, path="PATH", line="999").fullmatch(err.splitlines()[-1]) is not None


A_PACKAGE = {"module": "pkg/a/__init__.py", "new_name": "c"}
B_MODULE = {"module": "pkg/b.py", "new_name": "c"}


@pytest.mark.parametrize("entries", [[A_PACKAGE, B_MODULE], [B_MODULE, A_PACKAGE]], ids=["package-first", "module-first"])
def test_two_moves_ending_at_one_path_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], entries: Entries
) -> None:
    root = _project(tmp_path, {"pkg/a/__init__.py": "", "pkg/b.py": "Y = 1\n"}, entries)
    before = file_tree(root)
    code, out, err = run(root, _map(), monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert _refused_with_a_conflict_on("c", err, str(entries[1]["module"]), 2), err
    assert file_tree(root) == before


def test_two_packages_moved_onto_one_name_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"pkg/a/__init__.py": "", "pkg/a/x.py": "X = 1\n", "pkg/b/__init__.py": "", "pkg/b/y.py": "Y = 1\n"}
    root = _project(tmp_path, files, [{"module": "pkg/a/__init__.py", "new_name": "c"},
                                      {"module": "pkg/b/__init__.py", "new_name": "c"}])
    before = file_tree(root)
    code, out, err = run(root, _map(), monkeypatch, capsys)
    assert (code, out) == (1, "")
    assert _refused_with_a_conflict_on("c", err, "pkg/b/__init__.py", 2), err
    assert file_tree(root) == before


# ---- name conflicts


def test_a_module_meeting_a_binding_another_entry_introduces_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"pkg/__init__.py": "def x() -> int:\n    return 1\n", "pkg/a.py": "Y = 1\n"}
    root = _project(tmp_path, files, [{"module": "pkg/a.py", "new_name": "b"},
                                      {"file": "pkg/__init__.py", "symbol": "x", "new_name": "b"}])
    before = file_tree(root)
    code, out, err = run(root, _map(), monkeypatch, capsys)
    assert (code, out) == (1, "")
    refused = entry_refusal("pkg/a.py", _conflict("b", "pkg/__init__.py", 999))
    assert template_regex(refused, line="999").fullmatch(err.splitlines()[-1]), err
    assert file_tree(root) == before


def test_a_modules_new_name_capturing_a_reference_another_entry_rewrites_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"pkg/a.py": "X = 1\n", "pkg/use.py": "from pkg import a\n\nc = 2\n\n\ndef f() -> int:\n    return c\n"}
    root = _project(tmp_path, files, [{"module": "pkg/a.py", "new_name": "b"},
                                      {"file": "pkg/use.py", "symbol": "c", "new_name": "b"}])
    before = file_tree(root)
    code, out, err = run(root, _map(), monkeypatch, capsys)
    assert (code, out) == (1, "")
    refused = entry_refusal("LOCATOR", _conflict("b", "pkg/use.py", 999), 999)
    assert template_regex(refused, locator="LOCATOR", line="999").fullmatch(err.splitlines()[-1]), err
    assert file_tree(root) == before


def test_a_chain_of_module_names_is_refused_in_the_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {"pkg/a.py": "X = 1\n", "pkg/b.py": "Y = 1\n"},
                    [{"module": "pkg/a.py", "new_name": "b"}, {"module": "pkg/b.py", "new_name": "c"}])
    before = file_tree(root)
    refused = entry_refusal("pkg/a.py", _conflict("b", "pkg/b.py", 1))
    assert run_raw(root, _map(), monkeypatch, capsys) == (1, "", CHECKS + refused + "\n")
    assert file_tree(root) == before


def test_a_taken_module_name_is_refused_before_any_reference_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"pkg/a.py": "X = 1\n", "pkg/b.py": "Y = 1\n", "pkg/f.py": "def f() -> int:\n    return 1\n"}
    root = _project(tmp_path, files, [{"file": "pkg/f.py", "symbol": "f", "new_name": "g"},
                                      {"module": "pkg/a.py", "new_name": "b"}])
    before = file_tree(root)
    refused = entry_refusal("pkg/a.py", _conflict("b", "pkg/b.py", 1), 2)
    assert run_raw(root, _map(), monkeypatch, capsys) == (1, "", CHECKS + refused + "\n")
    assert file_tree(root) == before


def _case_insensitive(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Under `root`, `os.stat` finds an entry spelled in another case, as a case-insensitive filesystem does."""
    real_stat = os.stat

    def fold(path: str) -> str:
        if not path.startswith(str(root)) or os.path.lexists(path):
            return path
        parent, name = os.path.split(path)
        parent = fold(parent)
        entries = os.listdir(parent) if os.path.isdir(parent) else []
        return os.path.join(parent, next((e for e in entries if e.lower() == name.lower()), name))

    def stat(path: int | str | os.PathLike[str], *args: object, **kwargs: object) -> os.stat_result:
        return real_stat(path if isinstance(path, int) else fold(os.fspath(path)), *args, **kwargs)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(os, "stat", stat)


@pytest.mark.parametrize(("files", "module", "new_name"), [({"pkg/a.py": "X = 1\n"}, "pkg/a.py", "A"),
                                                          ({"pkg/a/__init__.py": "X = 1\n"}, "pkg/a/__init__.py", "A")],
                         ids=["module", "package"])
def test_a_case_only_rename_on_a_case_insensitive_filesystem_is_not_taken_by_itself(
    files: dict[str, str], module: str, new_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, files, [{"module": module, "new_name": new_name}])
    _case_insensitive(root, monkeypatch)
    code, _, err = run(root, _map(apply=False), monkeypatch, capsys)
    assert (code, err) == (0, ""), err


@pytest.mark.parametrize(("sibling", "named"), [("pkg/b.py", "pkg/B.py"), ("pkg/b/__init__.py", "pkg/B/__init__.py")],
                         ids=["module", "package"])
def test_another_file_spelling_the_new_name_in_another_case_takes_it(
    sibling: str, named: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {"pkg/a.py": "X = 1\n", sibling: "Y = 1\n"}, [{"module": "pkg/a.py", "new_name": "B"}])
    _case_insensitive(root, monkeypatch)
    before = file_tree(root)
    assert run_raw(root, _map(), monkeypatch, capsys) == (1, "", CHECKS + entry_refusal("pkg/a.py", _conflict("B", named, 1)) + "\n")
    assert file_tree(root) == before


USE_A = "from pkg import a\n\nprint(a.X)\n"


@pytest.mark.parametrize("new_name", ["a/b", "class", "1x", "b.py", "..", ""])
@pytest.mark.parametrize("entry", [{"module": "pkg/a.py"}, {"file": "pkg/use.py", "line": 1, "col": 17}], ids=["module", "located"])
def test_an_invalid_module_new_name_is_a_resolution_failure(
    entry: dict[str, object], new_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {"pkg/a.py": "X = 1\n", "pkg/use.py": USE_A}, [{**entry, "new_name": new_name}])
    before = file_tree(root)
    shown = "pkg/a.py" if "module" in entry else "pkg/use.py:1:17"
    refused = entry_refusal(shown, message("refactor.cannot-rename"))
    assert run_raw(root, _map(), monkeypatch, capsys) == (1, "", CHECKS + refused + "\n")
    assert file_tree(root) == before


def test_an_invalid_module_new_name_is_collected_with_the_other_resolution_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {"pkg/a.py": "X = 1\n", "pkg/use.py": USE_A},
                    [{"module": "pkg/a.py", "new_name": "class"}, {"file": "pkg/a.py", "symbol": "Missing", "new_name": "y"}])
    code, out, err = run_raw(root, _map(), monkeypatch, capsys)
    assert (code, out) == (2, "")
    lines = err.splitlines()
    assert lines[:3] == ["[resolve]", "[checks]", entry_refusal("pkg/a.py", message("refactor.cannot-rename"))]
    assert lines[3].startswith(entry_refusal("pkg/a.py Missing", "pkg/a.py: Missing names no declaration", 2))
    assert len(lines) == 4


# ---- stubs

STUB_FILES = {"pkg/a.py": "A = 1\n", "pkg/c.py": "C = 1\n", "pkg/e.py": "def f() -> int:\n    return 1\n",
              "pkg/sql/__init__.py": "", "nspkg/mod.py": "W = 1\n",
              "pkg/use.py": "from pkg import a, c\nimport json as js\nimport nspkg.mod\n\nprint(a.A, c.C, js, nspkg.mod.W)\n"}


def _stubbed(tmp_path: Path, entries: Entries) -> Path:
    config = (f"format: {current_format('living-architecture.yaml')}\nrefactor:\n  python:\n    moved_module_stub: |\n"
              '      raise_moved("{old}", "{new}", removal="{removal}")\n')
    root = _project(tmp_path, {**STUB_FILES, "living-architecture.yaml": config}, entries)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def test_every_moved_module_file_gets_a_stub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _stubbed(tmp_path, [{"module": "pkg/a.py", "new_name": "b"}, {"module": "pkg/c.py", "new_name": "d"},
                               {"file": "pkg/e.py", "symbol": "f", "new_name": "g"}])
    code, _out, err = run(root, _map("--stub", "2.0"), monkeypatch, capsys)
    assert (code, err) == (0, ""), err
    assert read(root, "pkg/a.py") == 'raise_moved("pkg.a", "pkg.b", removal="2.0")\n'
    assert read(root, "pkg/c.py") == 'raise_moved("pkg.c", "pkg.d", removal="2.0")\n'
    assert (read(root, "pkg/b.py"), read(root, "pkg/d.py")) == ("A = 1\n", "C = 1\n")
    assert read(root, "pkg/e.py") == "def g() -> int:\n    return 1\n"


def test_a_kept_move_gets_no_stub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _stubbed(tmp_path, [{"module": "pkg/a.py", "new_name": "b"}, {"module": "pkg/c.py", "new_name": "d"}])
    code, _out, err = run(root, _map("--stub", "2.0", "--keep", "pkg/c.py"), monkeypatch, capsys)
    assert (code, err) == (0, ""), err
    assert read(root, "pkg/a.py") == 'raise_moved("pkg.a", "pkg.b", removal="2.0")\n'
    assert read(root, "pkg/c.py") == "C = 1\n"
    assert not (root / "pkg" / "d.py").exists()


@pytest.mark.parametrize("other", [
    {"module": "pkg/sql/__init__.py", "new_name": "db"},
    {"file": "pkg/use.py", "offset": _offset(STUB_FILES["pkg/use.py"], "import json as "), "new_name": "jsn"},
    {"file": "pkg/use.py", "offset": STUB_FILES["pkg/use.py"].index("nspkg.mod"), "new_name": "nsp"},
], ids=["package", "library-alias", "namespace-package"])
def test_a_stub_is_refused_for_a_map_holding_a_package_namespace_package_or_alias_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], other: Mapping[str, object]
) -> None:
    root = _stubbed(tmp_path, [{"module": "pkg/a.py", "new_name": "b"}, other])
    before = file_tree(root)
    expected = (2, "", CHECKS + message("refactor.stub-not-module") + "\n")
    assert run_raw(root, _map("--stub", "2.0"), monkeypatch, capsys) == expected
    assert file_tree(root) == before


def test_a_stub_is_refused_for_a_map_renaming_no_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _stubbed(tmp_path, [{"file": "pkg/e.py", "symbol": "f", "new_name": "g"}])
    assert run_raw(root, _map("--stub", "2.0"), monkeypatch, capsys) == (
        2, "", CHECKS + message("refactor.stub-not-module") + "\n")


# ---- keeps over moves


def test_a_kept_module_inside_a_moved_package_moves_with_it_under_its_old_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, NESTED, [PACKAGE, CLIENT])
    code, _out, err = run(root, _map("--keep", "pkg/sql/client.py"), monkeypatch, capsys)
    assert (code, err) == (0, ""), err
    assert not (root / "pkg" / "sql").exists()
    assert read(root, "pkg/db/client.py") == "X = 1\n"
    assert read(root, "app.py") == "import pkg.db.cli\n\nprint(pkg.db.cli.X)\n"


def test_a_kept_package_keeps_the_moves_under_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, NESTED, [PACKAGE, CLIENT])
    before = _under(root, "pkg/")
    code, _out, err = run(root, _map("--keep", "pkg/sql"), monkeypatch, capsys)
    assert (code, err) == (0, ""), err
    assert _under(root, "pkg/") == before


def test_one_file_keep_matches_every_entrys_edits_in_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    use = "from pkg import a\nfrom pkg.f import f\n\nprint(a.X, f())\n"
    files = {"pkg/a.py": "X = 1\n", "pkg/f.py": "def f() -> int:\n    return 1\n", "pkg/use.py": use}
    root = _project(tmp_path, files, [{"module": "pkg/a.py", "new_name": "b"},
                                      {"file": "pkg/f.py", "symbol": "f", "new_name": "g"}])
    code, _out, err = run(root, _map("--keep", "pkg/use.py"), monkeypatch, capsys)
    assert (code, err) == (0, ""), err
    assert read(root, "pkg/use.py") == use
    assert read(root, "pkg/b.py") == "X = 1\n"
    assert read(root, "pkg/f.py") == "def g() -> int:\n    return 1\n"


# ---- stand-ins

STAND_IN = """\
class A:
    def save(self) -> int:
        return 1


class Other:
    def save(self) -> int:
        return 2


def use(a: A, o: Other) -> int:
    return a.save() + o.save()
"""


def test_a_classification_site_on_a_map_with_a_module_entry_is_classified_by_the_other_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {"pkg/a.py": "X = 1\n", "pkg/m.py": STAND_IN}, [
        {"module": "pkg/a.py", "new_name": "b"}, {"file": "pkg/m.py", "symbol": "A.save", "new_name": "store"},
    ])
    code, _out, err = run(root, _map("--without", "pkg/m.py:7"), monkeypatch, capsys)
    assert (code, err) == (0, ""), err
    assert (root / "pkg" / "b.py").is_file()
    assert read(root, "pkg/m.py") == STAND_IN.replace("    def save(self) -> int:\n        return 1",
                                                      "    def store(self) -> int:\n        return 1").replace(
        "a.save()", "a.store()")


def test_classification_sites_on_a_map_of_module_entries_only_are_refused_in_the_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {"pkg/a.py": "X = 1\n", "pkg/c.py": "Y = 1\n", "pkg/m.py": STAND_IN}, [
        {"module": "pkg/a.py", "new_name": "b"}, {"module": "pkg/c.py", "new_name": "d"},
    ])
    expected = CHECKS + message("refactor.not-stand-in", site="pkg/m.py:7") + "\n"
    assert run_raw(root, _map("--with", "pkg/m.py:7"), monkeypatch, capsys) == (2, "", expected)


# ---- phases and the language server


def test_a_map_of_a_module_and_a_function_prints_both_entries_and_one_rules_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _project(tmp_path, {"pkg/a.py": "X = 1\n", "pkg/f.py": "def f() -> int:\n    return 1\n"},
                    [{"module": "pkg/a.py", "new_name": "b"}, {"file": "pkg/f.py", "symbol": "f", "new_name": "g"}])
    code, _out, err = run_raw(root, _map(apply=False), monkeypatch, capsys)
    assert code == 0
    assert err == CHECKS + (
        "[references]\n[references 1/2] entry 1: a -> b\n[references 2/2] entry 2: f -> g\n"
        "[rules]\n[rules 1/1] entry 2: f -> g: clean\n[conflicts]\n"
    )


def _starts(monkeypatch: pytest.MonkeyPatch) -> list[None]:
    starts: list[None] = []
    original = LanguageServer.__enter__

    def counting(self: LanguageServer) -> LanguageServer:
        starts.append(None)
        return original(self)

    monkeypatch.setattr(LanguageServer, "__enter__", counting)
    return starts


def test_a_map_of_module_entries_only_starts_no_language_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    starts = _starts(monkeypatch)
    root = _project(tmp_path, {"pkg/a.py": "X = 1\n", "pkg/c.py": "Y = 1\n"},
                    [{"module": "pkg/a.py", "new_name": "b"}, {"module": "pkg/c.py", "new_name": "d"}])
    code, _out, err = run_raw(root, _map(apply=False), monkeypatch, capsys)
    assert code == 0, err
    assert starts == []
    assert "[rules]" not in err.splitlines()


def test_a_map_of_a_module_and_a_symbol_starts_the_language_server_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    starts = _starts(monkeypatch)
    root = _project(tmp_path, {"pkg/a.py": "X = 1\n", "pkg/f.py": "def f() -> int:\n    return 1\n"},
                    [{"module": "pkg/a.py", "new_name": "b"}, {"file": "pkg/f.py", "symbol": "f", "new_name": "g"}])
    assert run(root, _map(apply=False), monkeypatch, capsys)[0] == 0
    assert len(starts) == 1
