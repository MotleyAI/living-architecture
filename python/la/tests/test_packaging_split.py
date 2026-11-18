"""The two wheels install into a clean environment and carry their contracts; la's install exposes the dr commands."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from deterministic_refactor.contract import compute_hash

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir())
PACKAGES = {"dr": "deterministic-refactor", "la": "living-architecture"}


def _manifest(package: str) -> set[str]:
    return set(yaml.safe_load((REPO_ROOT / "shared" / package / "cli.yaml").read_text(encoding="utf-8"))["commands"])


@pytest.fixture(scope="module")
def dist(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("dist")
    for name in PACKAGES.values():
        subprocess.run(["uv", "build", "--package", name, "--out-dir", str(out)], cwd=REPO_ROOT / "python",
                       check=True, capture_output=True)
    return out


def _wheel(dist: Path, name: str) -> Path:
    [wheel] = dist.glob(f"{name.replace('-', '_')}-*.whl")
    return wheel


def _venv(where: Path) -> Path:
    subprocess.run(["uv", "venv", "--python", sys.executable, str(where)], check=True, capture_output=True)
    return where / "bin"


def _install(bin_dir: Path, dist: Path, *artifacts: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "pip", "install", "--python", str(bin_dir / "python"), "--no-index", "--find-links", str(dist),
         *map(str, artifacts)],
        capture_output=True, text=True, check=False,
    )


def _run(bin_dir: Path, *argv: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PATH": os.pathsep.join([str(bin_dir), os.environ["PATH"]])}
    return subprocess.run([str(bin_dir / argv[0]), *argv[1:]], cwd=cwd, env=env, capture_output=True, text=True,
                          check=False)


def test_dr_installs_alone_and_carries_its_contract(dist: Path, tmp_path: Path) -> None:
    bin_dir = _venv(tmp_path / "venv")
    proc = _install(bin_dir, dist, _wheel(dist, PACKAGES["dr"]))
    assert proc.returncode == 0, proc.stderr
    assert {p.name for p in bin_dir.iterdir()} >= _manifest("dr")
    assert not any((bin_dir / command).exists() for command in _manifest("la"))
    done = _run(bin_dir, "dr-doctor", "--contract-hash", cwd=tmp_path)
    assert done.stdout == f"{compute_hash(REPO_ROOT / 'shared' / 'dr')}\n", done.stderr


def test_la_install_resolves_dr(dist: Path, tmp_path: Path) -> None:
    bin_dir = _venv(tmp_path / "venv")
    proc = _install(bin_dir, dist, _wheel(dist, PACKAGES["la"]))
    assert proc.returncode == 0, proc.stderr
    assert PACKAGES["dr"] in proc.stderr
    assert {p.name for p in bin_dir.iterdir()} >= _manifest("dr") | _manifest("la")
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=work, check=True)
    hashes = {package: _run(bin_dir, f"{package}-doctor", "--contract-hash", cwd=work).stdout for package in PACKAGES}
    assert hashes == {package: f"{compute_hash(REPO_ROOT / 'shared' / package)}\n" for package in PACKAGES}
    assert _run(bin_dir, "la-config", "show", cwd=work).returncode == 0
    assert _run(bin_dir, "dr-config", "show", cwd=work).returncode == 0


def test_uv_tool_install_with_dr_executables_exposes_both_command_sets(dist: Path, tmp_path: Path) -> None:
    env = {**os.environ, "UV_TOOL_DIR": str(tmp_path / "tools"), "UV_TOOL_BIN_DIR": str(tmp_path / "bin")}
    proc = subprocess.run(
        ["uv", "tool", "install", "--python", sys.executable, "--no-index", "--find-links", str(dist),
         str(_wheel(dist, PACKAGES["la"])), "--with-executables-from", PACKAGES["dr"]],
        env=env, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert {p.name for p in (tmp_path / "bin").iterdir()} == _manifest("dr") | _manifest("la")
