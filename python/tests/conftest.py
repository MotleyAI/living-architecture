import importlib.util
import json
import os
import subprocess
from collections.abc import Callable
from functools import cache
from pathlib import Path

import fake_gh_cli
import pytest
from rope.refactor import patchedast

from living_architecture.contract import snapshot_dir

SCRIPTS_DIR = snapshot_dir() / "scripts"


def pytest_configure(config: pytest.Config) -> None:
    """Golden updates write from one process: undo xdist's `-n`, even an explicit one."""
    if os.environ.get("LA_UPDATE_GOLDENS") == "1":
        config.option.numprocesses = 0
        config.option.dist = "no"
        config.option.tx = []


class FakeGh:
    def __init__(self, tmp_path: Path) -> None:
        self.bin = tmp_path / "fakebin"
        self.bin.mkdir()
        self.routes_file = tmp_path / "routes.json"
        self.log_file = tmp_path / "gh.log"
        self.tmp = tmp_path
        fake_gh_cli.install(self.bin)
        self.route()

    def route(self, *routes: tuple[list[str], object] | tuple[list[str], object, int] | dict) -> None:
        """Each route: (argv tokens, stdout as str or JSON-able, [exit code]), or a case-format route dict."""
        specs = [r if isinstance(r, dict) else {"match": r[0], "stdout": r[1], "exit": r[2] if len(r) > 2 else 0}
                 for r in routes]
        fake_gh_cli.write_routes(self.routes_file, specs)

    def calls(self) -> list[dict]:
        if not self.log_file.exists():
            return []
        return [json.loads(line) for line in self.log_file.read_text().splitlines()]

    def env(self) -> dict[str, str]:
        return {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "FAKE_GH_ROUTES": str(self.routes_file),
            "FAKE_GH_LOG": str(self.log_file),
            "TMPDIR": str(self.tmp),
        }


@pytest.fixture
def fake_gh(tmp_path: Path) -> FakeGh:
    return FakeGh(tmp_path)


@pytest.fixture
def run_script(fake_gh: FakeGh) -> Callable[..., subprocess.CompletedProcess[str]]:
    def run(script: str, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPTS_DIR / script), *args],
            input=stdin if stdin is not None else "",
            capture_output=True,
            text=True,
            env=fake_gh.env(),
            cwd=fake_gh.tmp,
            timeout=90,
            check=False,
        )

    return run


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
