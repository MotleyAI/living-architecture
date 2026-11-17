"""One PyO3 abi3 wheel serves as an importable module and as `dr-*` console scripts."""

from __future__ import annotations

import subprocess
from functools import cache
from pathlib import Path

import pytest
from conftest import RUST

HELLO = RUST / "hello"
MODULE = "dr_hello"
SCRIPTS = ("dr-hello", "dr-hello-two")


@cache
def wheel(out: Path) -> tuple[Path | None, str]:
    """The wheel maturin builds into `out`; None and its error output when the build fails."""
    done = subprocess.run(["uvx", "maturin", "build", "--release", "--manifest-path", str(HELLO / "Cargo.toml"),
                           "--out", str(out)], capture_output=True, text=True, check=False)
    found = sorted(out.glob("*.whl"))
    return (found[0] if done.returncode == 0 and len(found) == 1 else None), done.stderr


@pytest.fixture(scope="module")
def build(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path | None, str]:
    return wheel(tmp_path_factory.mktemp("wheel"))


def _built(build: tuple[Path | None, str]) -> Path:
    found, error = build
    assert found is not None, f"maturin built no single wheel: {error[-2000:]}"
    return found


def test_wheel_is_abi3_for_python_311(build: tuple[Path | None, str]) -> None:
    assert "-cp311-abi3-" in _built(build).name


@pytest.mark.parametrize("version", ["3.11", "3.14"])
def test_wheel_installs_and_serves_module_and_scripts(build: tuple[Path | None, str], tmp_path: Path, version: str) -> None:
    built = _built(build)
    venv = tmp_path / "venv"
    subprocess.run(["uv", "venv", "-q", "--python", version, str(venv)], check=True)
    subprocess.run(["uv", "pip", "install", "-q", "--python", str(venv / "bin" / "python"), str(built)], check=True)
    module = subprocess.run([str(venv / "bin" / "python"), "-c", f"import {MODULE}; print({MODULE}.greeting())"],
                            capture_output=True, text=True, check=True).stdout
    assert module.strip()
    for script in SCRIPTS:
        assert subprocess.run([str(venv / "bin" / script)], capture_output=True, text=True, check=True).stdout == module
