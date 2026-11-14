"""Python member renames: the blind-spot and stand-in refusals, `--with` / `--without`, and `--keep`."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from project_files import file_tree

from living_architecture.cli import dr_refactor
from living_architecture.contract import message
from living_architecture.lang import LanguageServer

MakeProject = Callable[..., Path]

STORE = 'class Storage:\n    def get_model(self, name: str) -> int:\n        return 1\n'
USE = 'from pkg.store import Storage\n\n\ndef f(s: Storage) -> int:\n    return s.get_model("a")\n'
UNTYPED_TEST = 'def test_a(storage):\n    storage.get_model("m")\n'

BACKEND = """\
from typing import cast


class StorageBackend:
    def get_model(self, name: str) -> int:
        return 1


class _ModelReadCache:
    def __init__(self, inner: StorageBackend) -> None:
        self.inner = inner

    def get_model(self, name: str) -> int:
        return self.inner.get_model(name)


class _SubCache(_ModelReadCache):
    def get_model(self, name: str) -> int:
        return 2


def cached(inner: StorageBackend) -> StorageBackend:
    return cast(StorageBackend, _ModelReadCache(inner))
"""
BACKEND_USE = """\
from pkg.store import StorageBackend, _ModelReadCache


def f(s: StorageBackend, c: _ModelReadCache) -> int:
    return s.get_model("a") + c.get_model("b")
"""
UNRELATED = 'class Unrelated:\n    def get_model(self) -> str:\n        return ""\n\n\ndef g(u: Unrelated) -> str:\n    return u.get_model()\n'


@pytest.fixture
def project(typed_project: MakeProject, monkeypatch: pytest.MonkeyPatch) -> MakeProject:
    """`typed_project`, entered as the working directory so `--keep` / `--with` paths are project-relative."""

    def make(files: dict[str, str], **kw: object) -> Path:
        root = typed_project(files, **kw)
        monkeypatch.chdir(root)
        return root

    return make


def _rename(root: Path, rel: str, needle: str, new_name: str, *flags: str, apply: bool = True) -> int:
    offset = (root / rel).read_text(encoding="utf-8").index(needle)
    return dr_refactor(["--project", str(root), *(["--apply"] if apply else []), "rename", "--file", rel,
                        "--offset", str(offset), "--new-name", new_name, *flags])


def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def _blindspot(path: str, line: int, receiver: str, kind: str = "Unknown", attr: str = "get_model") -> str:
    return message("compliance.attr-blindspot", path=path, line=line, receiver=receiver, attr=attr, type=kind)


def _closing(count: int, attr: str = "get_model") -> str:
    return message("refactor.blindspots", count=count, attr=attr)


def _stand_in(path: str, line: int, cls: str, attr: str = "get_model") -> str:
    return message("refactor.stand-in", path=path, line=line, cls=cls, attr=attr)


# ---- blind spots


@pytest.mark.parametrize("apply", [False, True], ids=["dry-run", "apply"])
def test_untyped_fixture_parameter_refuses_the_rename(
    project: MakeProject, capsys: pytest.CaptureFixture[str], apply: bool
) -> None:
    root = project({"pkg/store.py": STORE, "pkg/use.py": USE, "tests/test_a.py": UNTYPED_TEST})
    before = file_tree(root)
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset", apply=apply) == 1
    assert capsys.readouterr() == ("", f"{_blindspot('tests/test_a.py', 2, 'storage')}\n{_closing(1)}\n")
    assert file_tree(root) == before


def test_blind_spots_sort_by_path_line_and_column(project: MakeProject, capsys: pytest.CaptureFixture[str]) -> None:
    root = project({
        "pkg/store.py": STORE,
        "tests/test_b.py": "from typing import Any\n\n\ndef test_b(x: Any, y):\n    y.get_model(); x.get_model()\n",
        "tests/test_a.py": UNTYPED_TEST,
    })
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset") == 1
    assert capsys.readouterr().err.splitlines() == [
        _blindspot("tests/test_a.py", 2, "storage"),
        _blindspot("tests/test_b.py", 5, "y"),
        _blindspot("tests/test_b.py", 5, "x", "Any"),
        _closing(3),
    ]


def test_allow_blindspots_proceeds_and_still_lists_them(
    project: MakeProject, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project({"pkg/store.py": STORE, "pkg/use.py": USE, "tests/test_a.py": UNTYPED_TEST})
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset", "--allow-blindspots") == 0
    assert capsys.readouterr().err == _blindspot("tests/test_a.py", 2, "storage") + "\n"
    assert _read(root, "pkg/store.py") == STORE.replace("get_model", "get_dataset")
    assert _read(root, "pkg/use.py") == USE.replace("get_model", "get_dataset")
    assert _read(root, "tests/test_a.py") == UNTYPED_TEST


def test_a_kept_blind_spot_does_not_block(project: MakeProject, capsys: pytest.CaptureFixture[str]) -> None:
    root = project({"pkg/store.py": STORE, "pkg/use.py": USE, "tests/test_a.py": UNTYPED_TEST})
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset", "--keep", "tests/test_a.py:2") == 0
    assert capsys.readouterr().err == ""
    assert _read(root, "pkg/use.py") == USE.replace("get_model", "get_dataset")
    assert _read(root, "tests/test_a.py") == UNTYPED_TEST


def test_untyped_mock_fixture_callee_is_a_blind_spot(project: MakeProject, capsys: pytest.CaptureFixture[str]) -> None:
    test = (
        "from pkg.store import Storage\n\n"
        "engine = Storage()\n\n\n"
        "def test_b(mocker):\n"
        '    mocker.patch.object(engine, "get_model")\n'
    )
    root = project({"pkg/store.py": STORE, "tests/test_b.py": test})
    before = file_tree(root)
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset") == 1
    assert capsys.readouterr().err == f"{_blindspot('tests/test_b.py', 7, 'engine')}\n{_closing(1)}\n"
    assert file_tree(root) == before


@pytest.mark.parametrize(
    ("rel", "needle"),
    [("pkg/funcs.py", "old"), ("pkg/funcs.py", "arg")],
    ids=["module-level-function", "parameter"],
)
def test_non_member_renames_are_not_scanned(project: MakeProject, rel: str, needle: str) -> None:
    funcs = "def old(arg: int) -> int:\n    return arg\n"
    untyped = "def f(x, y):\n    return x.old, y.arg\n"
    root = project({"pkg/funcs.py": funcs, "pkg/loose.py": untyped})
    assert _rename(root, rel, needle, "renamed") == 0
    assert _read(root, "pkg/loose.py") == untyped


def test_typed_receivers_do_not_block(project: MakeProject, capsys: pytest.CaptureFixture[str]) -> None:
    root = project({"pkg/store.py": STORE, "pkg/use.py": USE})
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset") == 0
    assert capsys.readouterr().err == ""


def test_the_blind_spot_scan_shares_the_language_server_session(
    project: MakeProject, monkeypatch: pytest.MonkeyPatch
) -> None:
    starts: list[None] = []
    original = LanguageServer.__enter__

    def counting(self: LanguageServer) -> LanguageServer:
        starts.append(None)
        return original(self)

    monkeypatch.setattr(LanguageServer, "__enter__", counting)
    root = project({"pkg/store.py": STORE, "pkg/use.py": USE, "tests/test_a.py": UNTYPED_TEST})
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset", "--allow-blindspots") == 0
    assert len(starts) == 1


# ---- stand-ins


@pytest.mark.parametrize("apply", [False, True], ids=["dry-run", "apply"])
def test_cast_stand_in_refuses_until_classified(
    project: MakeProject, capsys: pytest.CaptureFixture[str], apply: bool
) -> None:
    root = project({"pkg/store.py": BACKEND, "pkg/use.py": BACKEND_USE})
    before = file_tree(root)
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset", apply=apply) == 1
    assert capsys.readouterr() == (
        "", f"{_stand_in('pkg/store.py', 13, '_ModelReadCache')}\n{_stand_in('pkg/store.py', 18, '_SubCache')}\n"
    )
    assert file_tree(root) == before


def test_with_renames_the_stand_in_and_its_hierarchy_in_the_same_diff(
    project: MakeProject, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project({"pkg/store.py": BACKEND, "pkg/use.py": BACKEND_USE})
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset", "--with", "pkg/store.py:13") == 0
    assert capsys.readouterr().err == ""
    assert _read(root, "pkg/store.py") == BACKEND.replace("get_model", "get_dataset")
    assert _read(root, "pkg/use.py") == BACKEND_USE.replace("get_model", "get_dataset")


def test_without_leaves_the_stand_in_and_its_hierarchy(project: MakeProject) -> None:
    root = project({"pkg/store.py": BACKEND, "pkg/use.py": BACKEND_USE, "pkg/other.py": UNRELATED})
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset",
                   "--without", "pkg/store.py:13", "--without", "pkg/other.py:2") == 0
    assert _read(root, "pkg/store.py") == BACKEND.replace(
        "    def get_model(self, name: str) -> int:\n        return 1\n",
        "    def get_dataset(self, name: str) -> int:\n        return 1\n",
    ).replace("self.inner.get_model(name)", "self.inner.get_dataset(name)")
    assert _read(root, "pkg/use.py") == BACKEND_USE.replace('s.get_model("a")', 's.get_dataset("a")')
    assert _read(root, "pkg/other.py") == UNRELATED


def test_every_unclassified_stand_in_is_listed(project: MakeProject, capsys: pytest.CaptureFixture[str]) -> None:
    root = project({"pkg/store.py": BACKEND, "pkg/other.py": UNRELATED})
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset", "--without", "pkg/store.py:13") == 1
    assert capsys.readouterr() == ("", _stand_in("pkg/other.py", 2, "Unrelated") + "\n")


def test_several_with_stand_ins_sharing_references(project: MakeProject, capsys: pytest.CaptureFixture[str]) -> None:
    caches = (
        "from pkg.store import Storage\n\n\n"
        "class CacheA:\n    def get_model(self, name: str) -> int:\n        return 1\n\n\n"
        "class CacheB:\n    def get_model(self, name: str) -> int:\n        return 2\n\n\n"
        "def h(x: CacheA | CacheB, s: Storage) -> int:\n"
        '    """Calls ``get_model`` on either cache."""\n'
        '    return x.get_model("a") + s.get_model("b")\n'
    )
    root = project({"pkg/store.py": STORE, "pkg/caches.py": caches})
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset", "--docs",
                   "--with", "pkg/caches.py:5", "--with", "pkg/caches.py:10") == 0
    assert capsys.readouterr().err == ""
    assert _read(root, "pkg/caches.py") == caches.replace("get_model", "get_dataset")


@pytest.mark.parametrize("flag", ["--with", "--without"])
@pytest.mark.parametrize("site", ["pkg/store.py:5", "pkg/store.py:11", "pkg/store.py:99"],
                         ids=["hierarchy-line", "no-declaration", "past-the-end"])
def test_a_classification_line_without_a_stand_in(
    project: MakeProject, capsys: pytest.CaptureFixture[str], flag: str, site: str
) -> None:
    root = project({"pkg/store.py": BACKEND})
    before = file_tree(root)
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset", "--with", "pkg/store.py:13", flag, site) == 2
    assert capsys.readouterr() == ("", message("refactor.not-stand-in", site=site) + "\n")
    assert file_tree(root) == before


def test_one_classification_covers_every_stand_in_on_its_line(project: MakeProject) -> None:
    two = "class Two:\n    get_model = 0; get_model = 1\n"
    root = project({"pkg/store.py": STORE, "pkg/two.py": two})
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset", "--without", "pkg/two.py:2") == 0
    assert _read(root, "pkg/two.py") == two


@pytest.mark.parametrize("member", [
    "    get_model: int = 0\n",
    "    @property\n    def get_model(self) -> int:\n        return 0\n",
    "    def __init__(self) -> None:\n        self.get_model = 0\n",
    "    class get_model:\n        pass\n",
], ids=["field", "property", "self-attribute", "nested-class"])
def test_every_member_kind_is_a_stand_in(project: MakeProject, capsys: pytest.CaptureFixture[str], member: str) -> None:
    root = project({"pkg/store.py": STORE, "pkg/other.py": f"class Other:\n{member}"})
    line = 1 + f"class Other:\n{member}".split("get_model")[0].count("\n")
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset") == 1
    assert capsys.readouterr().err == _stand_in("pkg/other.py", line, "Other") + "\n"


def test_stand_ins_are_found_with_the_hierarchy_flag_off(
    project: MakeProject, capsys: pytest.CaptureFixture[str]
) -> None:
    root = project({"pkg/store.py": STORE, "pkg/other.py": UNRELATED})
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset", "--no-in-hierarchy") == 1
    assert capsys.readouterr().err == _stand_in("pkg/other.py", 2, "Unrelated") + "\n"


def test_an_override_is_not_a_stand_in_with_the_hierarchy_flag_off(project: MakeProject) -> None:
    source = "class A:\n    def run(self) -> int:\n        return 1\n\n\nclass B(A):\n    def run(self) -> int:\n        return 2\n"
    root = project({"pkg/a.py": source})
    assert _rename(root, "pkg/a.py", "run", "execute", "--no-in-hierarchy") == 0
    assert _read(root, "pkg/a.py") == source.replace("run", "execute", 1)


def test_both_refusals_under_apply_change_nothing(project: MakeProject, capsys: pytest.CaptureFixture[str]) -> None:
    root = project({"pkg/store.py": STORE, "pkg/other.py": UNRELATED, "tests/test_a.py": UNTYPED_TEST})
    before = file_tree(root)
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset") == 1
    assert capsys.readouterr() == ("", "".join(f"{line}\n" for line in [
        _blindspot("tests/test_a.py", 2, "storage"),
        _stand_in("pkg/other.py", 2, "Unrelated"),
        _closing(1),
    ]))
    assert file_tree(root) == before


def test_classifying_the_stand_ins_leaves_the_blind_spots(project: MakeProject, capsys: pytest.CaptureFixture[str]) -> None:
    loose = "def f(c):\n    return c.get_model()\n"
    root = project({"pkg/store.py": BACKEND, "pkg/loose.py": loose})
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset", "--with", "pkg/store.py:13") == 1
    assert capsys.readouterr().err == f"{_blindspot('pkg/loose.py', 2, 'c')}\n{_closing(1)}\n"


# ---- --keep


KEEP_USE = (
    "from pkg.store import Storage\n\n\n"
    "def f(s: Storage) -> int:\n"
    '    return s.get_model("a")\n\n\n'
    "def g(s: Storage) -> int:\n"
    '    return s.get_model("b")\n'
)


def test_a_kept_line_is_unchanged(project: MakeProject) -> None:
    root = project({"pkg/store.py": STORE, "tests/test_compat.py": KEEP_USE})
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset", "--keep", "tests/test_compat.py:9") == 0
    assert _read(root, "tests/test_compat.py") == KEEP_USE.replace('s.get_model("a")', 's.get_dataset("a")')


def test_kept_file_and_directory_match_whole_path_components(project: MakeProject) -> None:
    root = project({
        "pkg/store.py": STORE,
        "tests/compat/test_old.py": KEEP_USE,
        "tests/test_shim.py": KEEP_USE,
        "tests/compatible.py": KEEP_USE,
    })
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset",
                   "--keep", "tests/compat", "--keep", "tests/test_shim.py") == 0
    assert _read(root, "tests/compat/test_old.py") == KEEP_USE
    assert _read(root, "tests/test_shim.py") == KEEP_USE
    assert _read(root, "tests/compatible.py") == KEEP_USE.replace("get_model", "get_dataset")


def test_a_kept_path_is_normalized(project: MakeProject) -> None:
    root = project({"pkg/store.py": STORE, "tests/compat/test_old.py": KEEP_USE, "tests/other.py": KEEP_USE})
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset",
                   "--keep", str(root / "tests" / "other.py"), "--keep", "./tests/../tests/compat/") == 0
    assert _read(root, "tests/compat/test_old.py") == KEEP_USE
    assert _read(root, "tests/other.py") == KEEP_USE


def test_a_file_keep_and_a_line_keep_together(project: MakeProject) -> None:
    root = project({"pkg/store.py": STORE, "pkg/a.py": KEEP_USE})
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset", "--keep", "pkg/a.py", "--keep", "pkg/a.py:5") == 0
    assert _read(root, "pkg/a.py") == KEEP_USE


@pytest.mark.parametrize("site", ["pkg/a.py:99", "pkg/a.py:1", "pkg/missing.py", "docs"],
                         ids=["past-the-end", "untouched-line", "missing-file", "untouched-directory"])
def test_an_unmatched_keep(project: MakeProject, capsys: pytest.CaptureFixture[str], site: str) -> None:
    root = project({"pkg/store.py": STORE, "pkg/a.py": KEEP_USE, "docs/x.py": "y = 1\n"})
    before = file_tree(root)
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset", "--keep", site) == 2
    assert capsys.readouterr() == ("", message("refactor.keep-unmatched", site=site) + "\n")
    assert file_tree(root) == before


def test_keeping_a_declaration_does_not_keep_its_references(project: MakeProject) -> None:
    root = project({"pkg/store.py": STORE, "pkg/a.py": KEEP_USE})
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset", "--keep", "pkg/store.py:2") == 0
    assert _read(root, "pkg/store.py") == STORE
    assert _read(root, "pkg/a.py") == KEEP_USE.replace("get_model", "get_dataset")


def test_keep_drops_string_member_edits_too(project: MakeProject) -> None:
    use = 'from pkg.store import Storage\n\n\ndef f(s: Storage) -> object:\n    return getattr(s, "get_model")\n'
    root = project({"pkg/store.py": STORE, "pkg/a.py": use})
    assert _rename(root, "pkg/store.py", "get_model", "get_dataset", "--keep", "pkg/a.py:5") == 0
    assert _read(root, "pkg/a.py") == use
