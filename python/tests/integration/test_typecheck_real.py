"""la-typecheck with the real basedpyright from this project's venv."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

BIN_DIR = Path(sys.executable).parent


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
