"""la-typecheck with the real basedpyright from this project's venv."""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import basedpyright
import pytest

from living_architecture.config import current_format

BIN_DIR = Path(sys.executable).parent
REPRO = 'd: dict[str, int] = {"a": 1}\nfor k in ["a"]:\n    assert k in d, k\nx: str = d["a"]\n'
REPRO_ERROR = 'error: Type "int" is not assignable to declared type "str"'


def _typecheck(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PATH": f"{BIN_DIR}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run([str(BIN_DIR / "la-typecheck"), *args], cwd=root, env=env, capture_output=True, text=True,
                          check=False)


@pytest.mark.integration
def test_baseline_ratchet_with_real_basedpyright(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.0.0"\n', encoding="utf-8")
    module = tmp_path / "m.py"
    module.write_text('x: int = "a"\n', encoding="utf-8")

    written = _typecheck(tmp_path, "--write-baseline")
    assert written.returncode == 0, written.stdout + written.stderr
    assert (tmp_path / ".basedpyright" / "baseline.json").is_file()

    rerun = _typecheck(tmp_path)
    assert rerun.returncode == 0, rerun.stdout + rerun.stderr

    module.write_text('x: int = "a"\ny: int = "b"\n', encoding="utf-8")
    assert _typecheck(tmp_path).returncode == 1


def _repo(root: Path, files: dict[str, str], command: str | None = None) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    (root / "pyproject.toml").write_text('[project]\nname = "demo"\nversion = "0.0.0"\n', encoding="utf-8")
    if command is not None:
        config = f"format: {current_format()}\ncommands: {{typecheck: {{python: {command}}}}}\n"
        (root / "living-architecture.yaml").write_text(config, encoding="utf-8")
    for rel, text in files.items():
        (root / rel).write_text(text, encoding="utf-8")
    return root


@pytest.mark.integration
def test_dropped_diagnostic_is_reported(tmp_path: Path) -> None:
    proc = _typecheck(_repo(tmp_path, {"m.py": REPRO}))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert proc.stdout.count(REPRO_ERROR) == 1


@pytest.mark.integration
def test_worker_threads_are_patched(tmp_path: Path) -> None:
    root = _repo(tmp_path, {f"m{i}.py": REPRO for i in range(13)}, command="basedpyright --threads 4")
    proc = _typecheck(root)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert proc.stdout.count(REPRO_ERROR) == 13


@pytest.mark.integration
def test_wrapper_command_is_patched(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"m.py": REPRO}, command="./check.sh")
    wrapper = root / "check.sh"
    wrapper.write_text(f'#!/bin/sh\nexec "{BIN_DIR / "basedpyright"}" "$@"\n', encoding="utf-8")
    wrapper.chmod(0o755)
    proc = _typecheck(root)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert proc.stdout.count(REPRO_ERROR) == 1


def _digests(directory: Path) -> dict[str, str]:
    return {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


@pytest.mark.integration
def test_installed_basedpyright_is_untouched(tmp_path: Path) -> None:
    installed = Path(basedpyright.__file__).parent
    before = _digests(installed)
    proc = _typecheck(_repo(tmp_path, {"m.py": REPRO}))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert _digests(installed) == before
