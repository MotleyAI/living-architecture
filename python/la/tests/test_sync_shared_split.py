"""scripts/sync-shared vendors shared/trmv and shared/la into their four snapshots, each with its own hash."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from trmv.contract import compute_hash

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir())
SNAPSHOTS = {
    Path("python/trmv/src/trmv/contract/data"): "trmv",
    Path("python/la/src/living_architecture/contract/data"): "la",
    Path("node/trmv/src/contract/data"): "trmv",
    Path("node/la/src/contract/data"): "la",
}


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """scripts/ beside a small shared/trmv and shared/la, never synced."""
    shutil.copytree(REPO_ROOT / "scripts", tmp_path / "scripts")
    for package in ("trmv", "la"):
        (tmp_path / "shared" / package).mkdir(parents=True)
        (tmp_path / "shared" / package / "cli.yaml").write_text(f"commands: {{{package}-x: {{}}}}\n", encoding="utf-8")
    run = tmp_path / "shared" / "la" / "scripts" / "run.sh"
    run.parent.mkdir()
    run.write_text("#!/bin/sh\n", encoding="utf-8")
    run.chmod(0o755)
    return tmp_path


def _sync(tree: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(tree / "scripts" / "sync-shared"), *args], capture_output=True, text=True, check=False
    )


@pytest.mark.parametrize(("snapshot", "package"), SNAPSHOTS.items(), ids=str)
def test_sync_vendors_each_package_with_its_own_hash(tree: Path, snapshot: Path, package: str) -> None:
    assert _sync(tree).returncode == 0
    target = tree / snapshot
    assert sorted(p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()) == sorted(
        ["CONTRACT_HASH", "cli.yaml", *(["scripts/run.sh"] if package == "la" else [])]
    )
    assert (target / "cli.yaml").read_bytes() == (tree / "shared" / package / "cli.yaml").read_bytes()
    assert (target / "CONTRACT_HASH").read_text(encoding="utf-8") == compute_hash(tree / "shared" / package) + "\n"
    assert _sync(tree, "--check").returncode == 0


def test_executable_bit_is_preserved(tree: Path) -> None:
    assert _sync(tree).returncode == 0
    assert (tree / "python/la/src/living_architecture/contract/data/scripts/run.sh").stat().st_mode & 0o111


@pytest.mark.parametrize("package", ["trmv", "la"])
def test_check_names_only_the_stale_snapshots(tree: Path, package: str) -> None:
    assert _sync(tree).returncode == 0
    (tree / "shared" / package / "cli.yaml").write_text("commands: {}\n", encoding="utf-8")
    proc = _sync(tree, "--check")
    assert proc.returncode == 1
    assert "scripts/sync-shared" in proc.stderr
    for snapshot, owner in SNAPSHOTS.items():
        assert (str(snapshot) in proc.stderr) is (owner == package), snapshot


def test_check_reports_a_single_stale_snapshot(tree: Path) -> None:
    assert _sync(tree).returncode == 0
    stale = Path("node/la/src/contract/data")
    (tree / stale / "cli.yaml").write_text("changed\n", encoding="utf-8")
    proc = _sync(tree, "--check")
    assert proc.returncode == 1
    assert [line for line in proc.stderr.splitlines() if "stale" in line] == [f"stale: {stale}; run scripts/sync-shared"]
