"""la's static resolver: a package's own `from . import x` and a star import of a listed submodule reach the
submodule; a cyclic re-export stays unresolved."""

from __future__ import annotations

from pathlib import Path

import pytest

from living_architecture.refactor.patch_targets import SourceFolders
from living_architecture.refactor.python_project import ProjectLayout
from living_architecture.refactor.static_resolver import Resolver, Value


def _resolver(root: Path, files: dict[str, str]) -> Resolver:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")

    def finder(dotted: str) -> tuple[Path, bool] | None:
        base = root / dotted.replace(".", "/")
        if (base / "__init__.py").is_file():
            return base / "__init__.py", True
        return (base.with_suffix(".py"), False) if base.with_suffix(".py").is_file() else None

    return Resolver(finder)


@pytest.mark.parametrize(
    ("files", "module", "name", "value"),
    [
        ({"pkg/__init__.py": "from . import old\n", "pkg/old.py": "X = 1\n"}, "pkg", "old", ("module", "pkg.old")),
        ({"pkg/__init__.py": "from pkg import old\n", "pkg/old.py": "X = 1\n"}, "pkg", "old", ("module", "pkg.old")),
        ({"pkg/__init__.py": "from . import gone\n"}, "pkg", "gone", None),
        ({"pkg/__init__.py": "from pkg.a import x\n", "pkg/a.py": "from pkg import x\n", "pkg/x.py": "Y = 1\n"},
         "pkg.a", "x", None),
        ({"pkg/__init__.py": "", "pkg/sub/__init__.py": '__all__ = ["inner"]\n', "pkg/sub/inner.py": "Y = 1\n",
          "use.py": "from pkg.sub import *\n"}, "use", "inner", ("module", "pkg.sub.inner")),
        ({"pkg/__init__.py": "", "pkg/sub/__init__.py": "", "pkg/sub/inner.py": "Y = 1\n",
          "use.py": "from pkg.sub import *\n"}, "use", "inner", None),
        ({"m.py": "from m import x\n", "m/x.py": "Y = 1\n"}, "m", "x", None),
        ({"m.py": '__all__ = ["x"]\n', "m/x.py": "Y = 1\n", "use.py": "from m import *\n"}, "use", "x", None),
    ],
    ids=["own-relative-import", "own-absolute-import", "own-import-of-nothing", "cyclic-reexport", "star-listed-submodule",
         "star-unlisted-submodule",
         "module-shadowing-directory", "star-of-module-shadowing-directory"],
)
def test_a_module_attribute_resolves(tmp_path: Path, files: dict[str, str], module: str, name: str, value: Value) -> None:
    assert _resolver(tmp_path, files).member(module, name) == value


def _project_resolver(root: Path, files: dict[str, str]) -> Resolver:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    return Resolver(SourceFolders(ProjectLayout(root).source_folders()))


@pytest.mark.parametrize(
    ("files", "namespace", "attributes"),
    [
        ({"pkg/__init__.py": "", "pkg/ns/m.py": "Y = 1\n"}, "pkg.ns",
         [("pkg", "ns", ("module", "pkg.ns")), ("pkg.ns", "m", ("module", "pkg.ns.m"))]),
        ({"src/pkg/__init__.py": "", "src/pkg/ns/m.py": "Y = 1\n"}, "pkg.ns",
         [("pkg", "ns", ("module", "pkg.ns")), ("pkg.ns", "m", ("module", "pkg.ns.m"))]),
        ({"pkg/__init__.py": "", "pkg/ns/inner/m.py": "Y = 1\n"}, "pkg.ns.inner",
         [("pkg", "ns", ("module", "pkg.ns")), ("pkg.ns", "inner", ("module", "pkg.ns.inner")),
          ("pkg.ns.inner", "m", ("module", "pkg.ns.inner.m"))]),
        ({"pyproject.toml": '[tool.rope]\nsource_folders = ["a", "b"]\n', "a/ns/m.py": "Y = 1\n", "b/ns/m.py": "Y = 2\n",
          "b/ns/other.py": "Z = 1\n"}, "ns",
         [("ns", "m", None), ("ns", "other", ("module", "ns.other"))]),
    ],
    ids=["flat-layout", "src-layout", "nested", "submodule-in-two-portions"],
)
def test_a_namespace_package_resolves(tmp_path: Path, files: dict[str, str], namespace: str,
                                      attributes: list[tuple[str, str, Value]]) -> None:
    resolver = _project_resolver(tmp_path, files)
    module = resolver.load(namespace)
    assert module is not None
    assert (module.is_package, dict(module.scope.bindings), module.stars) == (True, {}, [])
    assert [(m, n, resolver.member(m, n)) for m, n, _ in attributes] == attributes


def test_a_module_shadows_a_namespace_directory(tmp_path: Path) -> None:
    resolver = _project_resolver(tmp_path, {"pkg/__init__.py": "", "pkg/ns.py": "Y = 1\n", "pkg/ns/m.py": "Y = 2\n"})
    module = resolver.load("pkg.ns")
    assert module is not None and module.is_package is False
    assert resolver.member("pkg.ns", "m") is None


def test_a_regular_package_shadows_a_namespace_portion(tmp_path: Path) -> None:
    resolver = _project_resolver(tmp_path, {"pyproject.toml": '[tool.rope]\nsource_folders = ["b", "a"]\n',
                                            "a/pkg/__init__.py": "X = 1\n", "b/pkg/extra.py": "Y = 1\n"})
    module = resolver.load("pkg")
    assert module is not None and module.is_package and module.path == (tmp_path / "a/pkg/__init__.py").resolve()
    assert resolver.member("pkg", "X") == ("decl", "pkg@1:0")
