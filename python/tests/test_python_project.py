"""la's ports of rope's project rules agree with rope itself: source folders, module names, module lookup and the
PEP-263 coding cookie."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from rope.base import libutils
from rope.base.fscommands import read_str_coding as rope_read_str_coding
from rope.base.project import Project

from living_architecture.refactor.python_project import ProjectLayout, read_str_coding

# Each layout: files (empty unless given) and symlinks (link -> target, relative to the root).
LAYOUTS: dict[str, tuple[dict[str, str], dict[str, str]]] = {
    "nested-packages": ({
        "pkg/__init__.py": "", "pkg/sub/__init__.py": "", "pkg/sub/m.py": "", "pkg/sub/deep/__init__.py": "",
        "tool.py": "",
    }, {}),
    "src-and-scripts": ({
        "src/app/__init__.py": "", "src/app/core.py": "", "scripts/run.py": "", "scripts/helpers/util.py": "",
    }, {}),
    "namespace-packages": ({"ns/m.py": "", "ns/inner/x.py": "", "top.py": ""}, {}),
    "package-beside-module": ({"pkg/__init__.py": "", "pkg/a.py": "", "pkg.py": "", "lib/pkg.py": ""}, {}),
    "stubs": ({
        "pkg/__init__.py": "", "pkg/stub.pyi": "", "pkg/both.py": "", "pkg/both.pyi": "", "typings/lib.pyi": "",
        "only_stubs/x.pyi": "",
    }, {}),
    "symlinked-directory": ({"real/pkg/__init__.py": "", "real/pkg/m.py": ""}, {"linked": "real"}),
    "duplicate-dotted-modules": ({
        "src/dup/__init__.py": "", "src/dup/a.py": "", "lib/dup/__init__.py": "", "lib/dup/b.py": "",
        "src/same.py": "", "lib/same.py": "",
    }, {}),
    "ignored-directories": ({
        "pkg/__init__.py": "", ".venv/lib/site/x/__init__.py": "", "venv/y/__init__.py": "", ".git/hooks/z.py": "",
        ".tox/t.py": "", ".mypy_cache/c.py": "", "build/b/__init__.py": "", "node_modules/n/__init__.py": "",
        "pkg/__pycache__/m.py": "",
    }, {}),
    "root-package": ({"__init__.py": "", "a.py": "", "sub/__init__.py": "", "sub/b.py": ""}, {}),
    "shadowing-installed": ({"yaml/__init__.py": "", "json.py": "", "app/main.py": ""}, {}),
}
MISSING = ["missing", "pkg.missing", "pkg.sub.missing.deeper", "yaml", "os", "os.path", "json", "collections.abc"]


def _layout(root: Path, name: str) -> Path:
    files, links = LAYOUTS[name]
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    for link, target in links.items():
        os.symlink(root / target, root / link, target_is_directory=True)
    return root


def _paths(root: Path) -> list[str]:
    """Every file and directory under `root` (symlinks followed), as relative paths."""
    out: list[str] = []
    for current, dirs, files in os.walk(root, followlinks=True):
        base = Path(current).relative_to(root)
        out += [(base / d).as_posix() for d in dirs] + [(base / f).as_posix() for f in files]
    return sorted(out)


@pytest.fixture(params=sorted(LAYOUTS))
def layout(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[tuple[Path, Project, ProjectLayout]]:
    root = _layout(tmp_path / "proj", request.param)
    # rope documents `ropefolder=None` (no rope folder); its signature infers `str` from the default.
    project = Project(str(root), ropefolder=None)  # pyright: ignore[reportArgumentType]
    yield root, project, ProjectLayout(root)
    project.close()


def test_source_folders_match_rope(layout: tuple[Path, Project, ProjectLayout]) -> None:
    _root, project, ours = layout
    assert ours.source_folders() == [Path(f.real_path) for f in project.get_source_folders()]


def test_module_names_match_rope(layout: tuple[Path, Project, ProjectLayout]) -> None:
    root, project, ours = layout
    paths = [rel for rel in _paths(root) if rel.endswith((".py", ".pyi")) or (root / rel).is_dir()]
    assert {rel: ours.modname(root / rel) for rel in paths} == {
        rel: libutils.modname(project.get_resource(rel)) for rel in paths}


def test_module_lookup_matches_rope(layout: tuple[Path, Project, ProjectLayout]) -> None:
    root, project, ours = layout
    dotted = sorted({libutils.modname(project.get_resource(rel)) for rel in _paths(root)} | set(MISSING))
    folders = [None, *project.get_source_folders(), project.root]

    def rope_find(name: str, folder: object) -> Path | None:
        found = project.find_module(name, folder=folder)
        return Path(found.real_path) if found is not None else None

    expected = {(name, i): rope_find(name, folder) for name in dotted for i, folder in enumerate(folders)}
    actual = {(name, i): ours.find_module(name, folder=Path(folder.real_path) if folder is not None else None)
              for name in dotted for i, folder in enumerate(folders)}
    assert actual == expected


COOKIES: list[bytes] = [
    b"# -*- coding: latin-1 -*-\nx = 1\n",
    b"#!/usr/bin/env python\n# vim: set fileencoding=utf-8 :\n",
    b"x = 1\ny = 2\n# coding: latin-1\n",
    b"x = 1\n",
    b"",
    b"# coding=  utf-8\n",
    b"# coding:\n",
    b"# coding: nosuch\n",
    b"\xef\xbb\xbf# coding: utf-8\n",
    b"# coding: latin-1\r\nx = 1\r\n",
    b"\t\f# coding: cp1252\n",
    b"x = 1  # coding: latin-1\n",
    b"# coding: utf_8.x-y\n",
]


@pytest.mark.parametrize("source", COOKIES, ids=range(len(COOKIES)))
def test_coding_cookie_matches_rope(source: bytes) -> None:
    assert read_str_coding(source) == rope_read_str_coding(source)
    text = source.decode("latin-1")
    assert read_str_coding(text) == rope_read_str_coding(text)
