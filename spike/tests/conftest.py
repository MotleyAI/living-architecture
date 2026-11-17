"""Runs the dumps of both sides over the corpora, once per session, and parametrizes the differentials."""

from __future__ import annotations

import subprocess
from functools import cache
from pathlib import Path

import pytest
from corpus import CONFORMANCE, DATA, REPO, SPIKE, py_files

VERSIONS = ("3.11", "3.12", "3.13", "3.14")
RUST = SPIKE / "rust"
TARGET = RUST / "target" / "release"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--slayer", type=Path, default=None, help="the SLayer copy to run the differentials over")


def corpora(config: pytest.Config) -> dict[str, Path]:
    """The corpora by name: the synthetic set, the conformance fixtures and, given `--slayer`, the SLayer copy."""
    found = {"data": DATA, "conformance": CONFORMANCE}
    slayer = config.getoption("--slayer")
    if slayer is not None:
        found["slayer"] = Path(slayer).resolve()
    return found


@cache
def files(root: Path) -> tuple[str, ...]:
    return tuple(py_files(root))


def _lines(stdout: str) -> dict[str, str]:
    """`REL<TAB>JSON` lines by REL, the JSON text kept byte for byte."""
    return dict(line.split("\t", 1) for line in stdout.splitlines() if "\t" in line)


@cache
def python_dumps(script: str, version: str, root: Path) -> dict[str, str]:
    """`spike/py/<script>` over every file of `root` under CPython `version`, by file."""
    command = ["uv", "run", "-q", "--isolated", "--no-project", "--python", version, "--with-editable", str(REPO / "python"),
               "python", str(SPIKE / "py" / script), "--root", str(root)]
    done = subprocess.run(command, input="\n".join(files(root)), capture_output=True, text=True, check=True)
    return _lines(done.stdout)


@cache
def rust_build() -> str | None:
    """Builds the Rust workspace; the build's error output when it fails."""
    done = subprocess.run(["cargo", "build", "--release", "--manifest-path", str(RUST / "Cargo.toml")],
                          capture_output=True, text=True, check=False)
    return None if done.returncode == 0 else done.stderr


@cache
def rust_dumps(binary: str, version: str, root: Path) -> tuple[dict[str, str], str]:
    """`binary` over every file of `root` for Python `version`, by file; and its error output."""
    error = rust_build()
    if error is not None:
        return {}, error
    done = subprocess.run([str(TARGET / binary), "--python-version", version, "--root", str(root)],
                          input="\n".join(files(root)), capture_output=True, text=True, check=False)
    return _lines(done.stdout), done.stderr


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "corpus_file" in metafunc.fixturenames:
        cases = [pytest.param((name, root, rel, version), id=f"{name}/{rel}@{version}",
                              marks=[pytest.mark.slayer] if name == "slayer" else [])
                 for name, root in corpora(metafunc.config).items() for rel in files(root) for version in VERSIONS]
        metafunc.parametrize("corpus_file", cases)
