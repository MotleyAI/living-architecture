"""Python dependency edges for `la-affected-tests`: every import, resolved to repo files by dotted suffix."""

from pathlib import Path

import pytest

from living_architecture import lang


def _edges(root: Path, files: dict[str, str], deleted: tuple[str, ...] = ()) -> set[tuple[str, str]]:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return set(lang.dependency_edges(root, files=sorted(files), deleted=sorted(deleted)))


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
