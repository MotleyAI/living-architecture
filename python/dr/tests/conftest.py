import importlib.util
import os
from collections.abc import Callable
from functools import cache
from pathlib import Path

import pytest
from rope.refactor import patchedast

import project_files
from deterministic_refactor.lang.language_server import LanguageServer


def pytest_configure(config: pytest.Config) -> None:
    """Golden updates write from one process: undo xdist's `-n`, even an explicit one."""
    if os.environ.get("LA_UPDATE_GOLDENS") == "1":
        config.option.numprocesses = 0
        config.option.dist = "no"
        config.option.tx = []


@pytest.fixture(autouse=True)
def cache_dir(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Each test's own occurrence-index cache, outside its project."""
    path = tmp_path_factory.mktemp("la-cache")
    monkeypatch.setenv("LA_CACHE_DIR", str(path))
    return path


@pytest.fixture
def typed_project(tmp_path: Path) -> Callable[..., Path]:
    """`project_files.write_project` at `<tmp>/proj`."""
    return lambda files, **kw: project_files.write_project(tmp_path / "proj", files, **kw)


@pytest.fixture
def no_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """Starting a language server fails the test."""

    def refuse(*_: object, **__: object) -> None:
        raise AssertionError("a language server was started")

    monkeypatch.setattr(LanguageServer, "__init__", refuse)


@cache
def _unpatched_walker() -> type:
    """rope's own `_PatchingASTWalker`, from a private copy of `patchedast` that no patch touches."""
    spec = importlib.util.spec_from_file_location("_unpatched_patchedast", patchedast.__file__)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._PatchingASTWalker


@pytest.fixture
def restore_rope_visitor(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], None]:
    """Put one of rope's own walker visitors back in place of its patch, for this test."""

    def restore(name: str) -> None:
        monkeypatch.setattr(patchedast._PatchingASTWalker, name, getattr(_unpatched_walker(), name))

    return restore


@pytest.fixture
def annotation_gap() -> str:
    """rope's own `_arg` leaves the line-3 annotation unwalked; the walk then drifts and crashes on line 8."""
    return (
        "from pkg.a import foo\n"
        "\n"
        'def f(p: F("(") = None):\n'
        "    a = 1\n"
        "    b = 2\n"
        "    c = 3\n"
        "    d = 4\n"
        "    e = foo()\n"
        "    return g(a)\n"
    )
