"""Test runners: the golden update mode runs serially; scripts/conformance-cross validates `--twin`."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

PYTHON_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PYTHON_ROOT.parent
CROSS = REPO_ROOT / "scripts" / "conformance-cross"
XDIST_STARTED = "created:"


def _corpus_smoke_run(*args: str, update: bool) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_") and k != "LA_UPDATE_GOLDENS"}
    if update:
        env["LA_UPDATE_GOLDENS"] = "1"
    test = "tests/test_conformance.py::test_corpus_is_not_empty"
    argv = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args, test]
    return subprocess.run(argv, cwd=PYTHON_ROOT, env=env, capture_output=True, text=True, check=False)


def test_update_mode_starts_no_xdist_workers_even_with_explicit_n() -> None:
    proc = _corpus_smoke_run("-n", "4", update=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert XDIST_STARTED not in proc.stdout
    assert "1 passed" in proc.stdout


def test_normal_mode_starts_xdist_workers_by_default() -> None:
    proc = _corpus_smoke_run(update=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert XDIST_STARTED in proc.stdout


def _cross(tmp_path: Path, *args: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Run scripts/conformance-cross with a fake `npm` that logs `<LA_CONFORMANCE_TWIN>|<args>` per call."""
    log = tmp_path / "npm.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    npm = fake_bin / "npm"
    npm.write_text(f'#!/bin/sh\necho "$LA_CONFORMANCE_TWIN|$*" >> "{log}"\n')
    npm.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.startswith("LA_CONFORMANCE_")}
    env["PATH"] = f"{fake_bin}{os.pathsep}{os.environ['PATH']}"
    proc = subprocess.run([str(CROSS), *args], env=env, capture_output=True, text=True, check=False)
    return proc, log.read_text().splitlines() if log.exists() else []


@pytest.mark.parametrize("args", [["--twin"], ["--twin", "nope"]], ids=["missing", "unknown"])
def test_conformance_cross_rejects_a_bad_twin_before_building(tmp_path: Path, args: list[str]) -> None:
    proc, npm_calls = _cross(tmp_path, *args)
    assert proc.returncode == 2
    assert "usage" in proc.stderr.lower()
    assert npm_calls == []


@pytest.mark.parametrize(
    ("args", "twins"),
    [
        ([], ["python", "typescript"]),
        (["--twin", "python"], ["python"]),
        (["--twin", "typescript"], ["typescript"]),
    ],
    ids=["both", "python", "typescript"],
)
def test_conformance_cross_runs_the_selected_twins_after_one_build(
    tmp_path: Path, args: list[str], twins: list[str]
) -> None:
    proc, npm_calls = _cross(tmp_path, *args, "-k", "smoke")
    assert proc.returncode == 0, proc.stderr
    assert npm_calls == ["|run --silent build", *(f"{t}|run --silent conformance -- -k smoke" for t in twins)]
