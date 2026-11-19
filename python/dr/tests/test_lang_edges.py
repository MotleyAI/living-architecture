"""Python dependency edges for `la-affected-tests`: every import, resolved to repo files by dotted suffix."""

import ast
import os
import threading
from pathlib import Path
from typing import Any

import pytest

from deterministic_refactor import lang


def _edges(
    root: Path, files: dict[str, str], deleted: tuple[str, ...] = (), extra: tuple[str, ...] = ()
) -> set[tuple[str, str]]:
    """Edges over `files` (written) plus `extra` graph files already on disk."""
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return set(lang.dependency_edges(root, files=sorted([*files, *extra]), deleted=sorted(deleted)))


def _targets(edges: set[tuple[str, str]], importer: str) -> set[str]:
    return {dst for src, dst in edges if src == importer}


def test_same_module_under_several_roots(tmp_path):
    edges = _edges(tmp_path, {"one/a/b.py": "", "two/a/b.py": "", "tests/test_x.py": "import a.b\n"})
    assert _targets(edges, "tests/test_x.py") == {"one/a/b.py", "two/a/b.py"}


def test_suffix_matches_at_a_directory_boundary_only(tmp_path):
    edges = _edges(tmp_path, {"lib/xa/b.py": "", "lib/a/b.py": "", "tests/test_x.py": "import a.b\n"})
    assert _targets(edges, "tests/test_x.py") == {"lib/a/b.py"}


def test_package_initializers_along_the_match(tmp_path):
    files = {"src/pkg/__init__.py": "", "src/pkg/sub/__init__.py": "", "src/pkg/sub/mod.py": "",
             "tests/test_x.py": "import pkg.sub.mod\n"}
    assert _targets(_edges(tmp_path, files), "tests/test_x.py") == {
        "src/pkg/__init__.py", "src/pkg/sub/__init__.py", "src/pkg/sub/mod.py"
    }


def test_from_import_also_resolves_the_name_as_a_module(tmp_path):
    files = {"lib/a/b/__init__.py": "", "lib/a/b/c.py": "", "tests/test_x.py": "from a.b import c\n"}
    assert {"lib/a/b/__init__.py", "lib/a/b/c.py"} <= _targets(_edges(tmp_path, files), "tests/test_x.py")


def test_module_and_package_of_the_same_name(tmp_path):
    files = {"x/m.py": "", "y/m/__init__.py": "", "tests/test_x.py": "import m\n"}
    assert _targets(_edges(tmp_path, files), "tests/test_x.py") == {"x/m.py", "y/m/__init__.py"}


def test_namespace_directories(tmp_path):
    files = {"ns/pkg/mod.py": "", "tests/test_x.py": "import pkg.mod\n"}
    assert _targets(_edges(tmp_path, files), "tests/test_x.py") == {"ns/pkg/mod.py"}


def test_own_package_chain_stops_at_the_first_directory_without_an_initializer(tmp_path):
    files = {"__init__.py": "", "a/b/__init__.py": "", "a/b/c/__init__.py": "", "a/b/c/m.py": ""}
    assert _targets(_edges(tmp_path, files), "a/b/c/m.py") == {"a/b/c/__init__.py", "a/b/__init__.py"}


def test_relative_imports_from_a_package_initializer(tmp_path):
    files = {"pkg/__init__.py": "", "pkg/y.py": "", "pkg/sub/__init__.py": "from . import x\nfrom .. import y\n",
             "pkg/sub/x.py": ""}
    assert {"pkg/sub/x.py", "pkg/y.py", "pkg/__init__.py"} <= _targets(_edges(tmp_path, files), "pkg/sub/__init__.py")


def test_relative_imports_from_a_module(tmp_path):
    files = {"pkg/__init__.py": "", "pkg/y.py": "", "pkg/sub/__init__.py": "", "pkg/sub/x.py": "",
             "pkg/sub/m.py": "from .x import f\nfrom ..y import g\n"}
    assert {"pkg/sub/x.py", "pkg/y.py"} <= _targets(_edges(tmp_path, files), "pkg/sub/m.py")


def test_excessive_relative_level_stays_inside_the_repo(tmp_path):
    files = {"pkg/__init__.py": "", "pkg/m.py": "from .... import z\nfrom ....q import r\n"}
    edges = _edges(tmp_path, files)
    assert {dst for _, dst in edges} <= set(files)


@pytest.mark.parametrize(
    "source",
    [
        "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    import pkg.b\n",
        "def f():\n    import pkg.b\n",
        "class C:\n    from pkg import b\n",
        "try:\n    import pkg.b\nexcept ImportError:\n    pass\n",
    ],
    ids=["type-checking", "in-function", "in-class", "in-try"],
)
def test_every_import_counts(tmp_path, source):
    files = {"src/pkg/__init__.py": "", "src/pkg/b.py": "", "tests/test_x.py": source}
    assert "src/pkg/b.py" in _targets(_edges(tmp_path, files), "tests/test_x.py")


@pytest.mark.parametrize(
    "source",
    [
        "import pkg.b\n",
        "from pkg \\\n    import b\n",
        "from pkg import (\n    a,\n    b,\n)\n",
        "from pkg.b import *\n",
        "import pkg.c as see, pkg.b\n",
        "import os; import pkg.b as bee\n",
    ],
    ids=["plain", "continuation", "parenthesized", "star", "alias-list", "semicolon"],
)
def test_lexical_scan_of_a_file_the_parser_rejects(tmp_path, source):
    files = {"src/pkg/__init__.py": "", "src/pkg/b.py": "", "src/pkg/c.py": "",
             "tests/test_x.py": source + "\ndef broken(:\n"}
    assert "src/pkg/b.py" in _targets(_edges(tmp_path, files), "tests/test_x.py")


def test_deleted_target_resolves(tmp_path):
    files = {"src/pkg/__init__.py": "", "tests/test_x.py": "from pkg import gone\n"}
    edges = _edges(tmp_path, files, deleted=("src/pkg/gone.py",))
    assert "src/pkg/gone.py" in _targets(edges, "tests/test_x.py")


def test_unresolved_imports_make_no_edge(tmp_path):
    edges = _edges(tmp_path, {"tests/test_x.py": "import os\nimport json.decoder\nfrom . import nothing\n"})
    assert _targets(edges, "tests/test_x.py") == set()


def test_edges_are_repo_relative_posix_pairs(tmp_path):
    files = {"src/pkg/__init__.py": "", "src/pkg/a.py": "from pkg import b\n", "src/pkg/b.py": ""}
    edges = _edges(tmp_path, files)
    assert ("src/pkg/a.py", "src/pkg/b.py") in edges
    assert all(not Path(p).is_absolute() and "\\" not in p for edge in edges for p in edge)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs FIFOs")
def test_a_file_that_is_not_regular_is_not_read(tmp_path):
    os.mkfifo(tmp_path / "pipe")
    root = tmp_path / "repo"
    (root / "tests").mkdir(parents=True)
    (root / "tests/test_pipe.py").symlink_to(tmp_path / "pipe")
    files = {"src/pkg/__init__.py": "", "src/pkg/b.py": "", "tests/test_a.py": "from pkg import b\n"}
    found: list[set[tuple[str, str]]] = []
    worker = threading.Thread(target=lambda: found.append(_edges(root, files, extra=("tests/test_pipe.py",))), daemon=True)
    worker.start()
    worker.join(timeout=30)
    assert found, "reading a FIFO blocked"
    assert _targets(found[0], "tests/test_pipe.py") == set()
    assert "src/pkg/b.py" in _targets(found[0], "tests/test_a.py")


def test_py_only_edges_unchanged(tmp_path):
    files = {
        "src/pkg/__init__.py": "from .a import f\n",
        "src/pkg/a.py": "import pkg.b\n",
        "src/pkg/b.py": "from pkg import c\n",
        "src/pkg/c.py": "",
        "src/pkg/sub/__init__.py": "",
        "src/pkg/sub/d.py": "from .. import b\nfrom pkg.sub import *\n",
        "tests/test_x.py": "from pkg.sub.d import g\n",
    }
    assert _edges(tmp_path, files) == {
        ("src/pkg/__init__.py", "src/pkg/a.py"),
        ("src/pkg/a.py", "src/pkg/__init__.py"),
        ("src/pkg/a.py", "src/pkg/b.py"),
        ("src/pkg/b.py", "src/pkg/__init__.py"),
        ("src/pkg/b.py", "src/pkg/c.py"),
        ("src/pkg/c.py", "src/pkg/__init__.py"),
        ("src/pkg/sub/__init__.py", "src/pkg/__init__.py"),
        ("src/pkg/sub/d.py", "src/pkg/__init__.py"),
        ("src/pkg/sub/d.py", "src/pkg/b.py"),
        ("src/pkg/sub/d.py", "src/pkg/sub/__init__.py"),
        ("tests/test_x.py", "src/pkg/__init__.py"),
        ("tests/test_x.py", "src/pkg/sub/__init__.py"),
        ("tests/test_x.py", "src/pkg/sub/d.py"),
    }


TARGET = "core/kinds.py"
DECLARES = 'from typing import Literal\n\nDriftKind = Literal["edit_model", "drop"]\n'
REEXPORT = "from core.kinds import DriftKind as DriftKind\n"


def _closure(files: dict[str, str], target: str = TARGET) -> set[str]:
    """The reverse closure of `target`, each file passed as its tree, or as text when it does not parse."""
    sources: dict[str, ast.Module | str] = {}
    for rel, text in {TARGET: DECLARES, **files}.items():
        try:
            sources[rel] = ast.parse(text)
        except SyntaxError:
            sources[rel] = text
    return lang.reverse_closure(target, sources)


def test_closure_holds_the_target_and_its_importers_only():
    files = {"core/__init__.py": "", "app/a.py": "from core.kinds import DriftKind\n", "app/b.py": "import app.a\n",
             "app/c.py": "import os\n", "app/d.py": "from core import other\n", "core/other.py": ""}
    assert _closure(files) == {TARGET, "app/a.py", "app/b.py"}


@pytest.mark.parametrize(
    "source",
    [
        "import core.kinds\n",
        "from core import kinds\n",
        "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from core.kinds import DriftKind\n",
        "def f():\n    from core.kinds import DriftKind\n",
        "class C:\n    from core.kinds import DriftKind\n",
        "import sys\n\nif sys.version_info >= (3, 99):\n    from core.kinds import DriftKind\n",
        "try:\n    from core.kinds import DriftKind\nexcept ImportError:\n    pass\n",
    ],
    ids=["import", "from-package", "type-checking", "in-function", "in-class", "conditional", "in-try"],
)
def test_closure_follows_every_import_statement(source):
    assert "app/use.py" in _closure({"core/__init__.py": "", "app/use.py": source})


def test_closure_through_a_chain_of_reexports():
    files = {"a/__init__.py": REEXPORT, "b/__init__.py": "from a import DriftKind as DriftKind\n",
             "app/use.py": "from b import DriftKind\n"}
    assert {"a/__init__.py", "b/__init__.py", "app/use.py"} <= _closure(files)


@pytest.mark.parametrize(
    ("rel", "source"),
    [("core/use.py", "from . import kinds\n"), ("core/use.py", "from .kinds import DriftKind\n"),
     ("core/sub/use.py", "from .. import kinds\n"), ("core/sub/use.py", "from ..kinds import DriftKind\n")],
    ids=["dot-name", "dot-module", "dotdot-name", "dotdot-module"],
)
def test_closure_through_a_relative_import(rel, source):
    assert rel in _closure({"core/__init__.py": "", "core/sub/__init__.py": "", rel: source})


def test_star_import_reaches_every_direct_submodule():
    files = {"core/__init__.py": '__all__ = ["kinds"]\n', "app/use.py": "from core import *\n"}
    assert "app/use.py" in _closure(files)


def test_closure_through_a_stub_module():
    files = {"shim.py": "", "shim.pyi": REEXPORT, "app/use.py": "from shim import DriftKind\n"}
    assert "app/use.py" in _closure(files)


def test_closure_through_a_package_initializer_stub():
    files = {"api/__init__.py": "", "api/__init__.pyi": REEXPORT, "app/use.py": "from api import DriftKind\n"}
    assert "app/use.py" in _closure(files)


@pytest.mark.parametrize("source", ["from . import x\n", "from .x import DriftKind\n"], ids=["name", "module"])
def test_closure_through_a_relative_import_of_a_stub(source):
    files = {"api/__init__.pyi": "", "api/x.pyi": REEXPORT, "api/use.py": source}
    assert "api/use.py" in _closure(files)


@pytest.mark.parametrize(
    ("stub", "source"),
    [("typings/vendor-stubs/__init__.pyi", "from vendor import DriftKind\n"),
     ("typings/vendor-stubs/sub.pyi", "import vendor.sub\n")],
    ids=["package", "submodule"],
)
def test_closure_through_a_stubs_directory(stub, source):
    assert "app/use.py" in _closure({stub: REEXPORT, "app/use.py": source})


def test_closure_through_a_namespace_package():
    files = {"ns/core/kinds.py": DECLARES, "app/use.py": "from core.kinds import DriftKind\n"}
    assert "app/use.py" in _closure(files, target="ns/core/kinds.py")


def test_a_builtins_stub_that_reaches_the_target_reaches_every_file():
    files = {"__builtins__.pyi": REEXPORT, "other/x.py": "def f() -> None: ...\n"}
    assert "other/x.py" in _closure(files)


def test_a_builtins_stub_that_does_not_reach_the_target_adds_nothing():
    files = {"__builtins__.pyi": "import os\n", "other/x.py": "def f() -> None: ...\n"}
    assert "other/x.py" not in _closure(files)


def test_a_file_that_does_not_parse_is_read_lexically():
    files = {"app/use.py": "from core.kinds import DriftKind\n\ndef broken(:\n"}
    assert "app/use.py" in _closure(files)


def test_parsed_trees_are_not_parsed_again(monkeypatch):
    trees: dict[str, ast.Module | str] = {
        TARGET: ast.parse(DECLARES), "app/use.py": ast.parse("from core.kinds import DriftKind\n")
    }
    parse = ast.parse
    calls: list[object] = []

    def counted(*args: Any, **kwargs: Any) -> ast.Module:
        calls.append(args)
        return parse(*args, **kwargs)

    monkeypatch.setattr(ast, "parse", counted)
    closure = lang.reverse_closure(TARGET, trees)
    monkeypatch.undo()
    assert (closure, calls) == ({TARGET, "app/use.py"}, [])
