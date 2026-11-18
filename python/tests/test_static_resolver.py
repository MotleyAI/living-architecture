"""la's static resolver: a package's own `from . import x` and a star import of a listed submodule reach the
submodule; a cyclic re-export stays unresolved; namespace packages resolve; each import item is recorded; `global`,
`nonlocal`, comprehension and walrus scopes bind where Python does."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from living_architecture.refactor.patch_targets import SourceFolders
from living_architecture.refactor.python_project import ProjectLayout
from living_architecture.refactor.static_resolver import Binder, Module, Resolver, Scope, Value


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
    assert module is not None
    assert module.is_package is False
    assert resolver.member("pkg.ns", "m") is None


def test_a_regular_package_shadows_a_namespace_portion(tmp_path: Path) -> None:
    resolver = _project_resolver(tmp_path, {"pyproject.toml": '[tool.rope]\nsource_folders = ["b", "a"]\n',
                                            "a/pkg/__init__.py": "X = 1\n", "b/pkg/extra.py": "Y = 1\n"})
    module = resolver.load("pkg")
    assert module is not None
    assert (module.is_package, module.path) == (True, (tmp_path / "a/pkg/__init__.py").resolve())
    assert resolver.member("pkg", "X") == ("decl", "pkg@1:0")


def test_the_binder_records_each_import_item_with_its_scope_and_guard() -> None:
    tree = ast.parse(
        "import a, b\nif TYPE_CHECKING:\n    from c import d\n\n\ndef f() -> None:\n    import e\n"
        "    try:\n        import g\n    except ImportError:\n        pass\n"
    )
    binder = Module(tree, ["m"], False).binder
    rows = [(stmt.lineno, item.index, item.scope.kind, type(item.guard).__name__ if item.guard else None)
            for stmt, _, _ in binder.imports for alias in stmt.names
            if (item := binder.import_items[id(alias)]).stmt is stmt]
    assert rows == [(1, 0, "module", None), (1, 1, "module", None), (3, 0, "module", "If"), (7, 0, "function", None),
                    (9, 0, "function", "Try")]


def _binder(text: str) -> Binder:
    return Module(ast.parse(text), ["m"], False).binder


def _reads(binder: Binder, line: int) -> list[Scope]:
    """The scopes of the `sub` loads on `line`, left to right."""
    found = [(n.col_offset, s) for n, s in binder.loads if isinstance(n, ast.Name) and n.lineno == line and n.id == "sub"]
    return [scope for _, scope in sorted(found, key=lambda pair: pair[0])]


def _owners(binder: Binder) -> list[Scope]:
    return [scope.owner(name) for scope, name, _ in binder.bound if name == "sub"]


def test_a_global_name_binds_in_the_module_scope() -> None:
    binder = _binder("import pkg.sub as sub\n\n\ndef f():\n    global sub\n    sub = None\n    return sub\n")
    [read] = _reads(binder, 7)
    assert read.resolving("sub") is binder.module
    assert _owners(binder) == [binder.module, binder.module]


def test_a_nonlocal_name_binds_in_the_enclosing_function_scope() -> None:
    binder = _binder(
        "def outer():\n    import pkg.sub as sub\n\n    def inner():\n        nonlocal sub\n        sub = None\n"
        "        return sub\n\n    return inner, sub\n"
    )
    [read] = _reads(binder, 7)
    [outer] = _reads(binder, 9)
    assert read.resolving("sub") is outer
    assert _owners(binder) == [outer, outer]


def test_a_comprehension_first_iterable_is_read_in_the_enclosing_scope() -> None:
    binder = _binder("import pkg.sub as sub\n\nitems = [sub for sub in sub.thing for x in sub]\n")
    element, first, later = _reads(binder, 3)
    assert first is binder.module
    assert element is later
    assert element is not binder.module
    assert element.resolving("sub") is element


def test_a_walrus_in_a_comprehension_binds_in_the_enclosing_function() -> None:
    binder = _binder("import pkg.sub as sub\n\n\ndef f(xs):\n    [(sub := v) for v in xs]\n    return sub\n")
    [read] = _reads(binder, 6)
    assert read.resolving("sub") is read
    assert read is not binder.module
