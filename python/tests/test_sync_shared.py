"""scripts/sync-shared: vendors shared/ into each twin's snapshot with its hash; --check reports staleness."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from living_architecture.contract import compute_hash

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SNAPSHOT_REL = Path("python/src/living_architecture/contract/data")
NODE_SNAPSHOT_REL = Path("node/src/contract/data")
SNAPSHOTS = [SNAPSHOT_REL, NODE_SNAPSHOT_REL]
TWINS = ["python", "node"]


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A copy of just what sync-shared reads and writes (node parts only where they exist yet)."""
    for rel in ("scripts", "shared", SNAPSHOT_REL):
        shutil.copytree(REPO_ROOT / rel, tmp_path / rel)
    (tmp_path / "node").mkdir()
    if (REPO_ROOT / NODE_SNAPSHOT_REL).is_dir():
        shutil.copytree(REPO_ROOT / NODE_SNAPSHOT_REL, tmp_path / NODE_SNAPSHOT_REL)
    for name in ("README.md", "LICENSE"):
        shutil.copy2(REPO_ROOT / name, tmp_path / name)
        for twin in TWINS:
            if (REPO_ROOT / twin / name).is_file():
                shutil.copy2(REPO_ROOT / twin / name, tmp_path / twin / name)
    return tmp_path


def _sync(tree: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(tree / "scripts" / "sync-shared"), *args], capture_output=True, text=True, check=False
    )


def test_check_passes_on_a_synced_tree(tree: Path) -> None:
    assert _sync(tree, "--check").returncode == 0


def test_check_fails_after_shared_changes_and_writes_nothing(tree: Path) -> None:
    (tree / "shared" / "findings.yaml").write_text("changed\n", encoding="utf-8")
    proc = _sync(tree, "--check")
    assert proc.returncode == 1
    assert "scripts/sync-shared" in proc.stderr
    assert (tree / SNAPSHOT_REL / "findings.yaml").read_text(encoding="utf-8") != "changed\n"


@pytest.mark.parametrize("snapshot_rel", SNAPSHOTS, ids=str)
def test_sync_copies_removes_and_rehashes(tree: Path, snapshot_rel: Path) -> None:
    (tree / "shared" / "new.yaml").write_text("x: 1\n", encoding="utf-8")
    (tree / "shared" / "regex-subset.md").unlink()
    assert _sync(tree).returncode == 0
    snapshot = tree / snapshot_rel
    assert (snapshot / "new.yaml").read_text(encoding="utf-8") == "x: 1\n"
    assert not (snapshot / "regex-subset.md").exists()
    assert (snapshot / "CONTRACT_HASH").read_text(encoding="utf-8") == compute_hash(tree / "shared") + "\n"
    assert _sync(tree, "--check").returncode == 0


def test_check_reports_a_stale_node_snapshot(tree: Path) -> None:
    assert _sync(tree).returncode == 0
    stale = tree / NODE_SNAPSHOT_REL / "findings.yaml"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("changed\n", encoding="utf-8")
    proc = _sync(tree, "--check")
    assert proc.returncode == 1
    assert str(NODE_SNAPSHOT_REL) in proc.stderr


@pytest.mark.parametrize("twin", TWINS)
def test_sync_vendors_the_root_files(tree: Path, twin: str) -> None:
    (tree / "README.md").write_text("new readme\n", encoding="utf-8")
    assert _sync(tree, "--check").returncode == 1
    assert _sync(tree).returncode == 0
    assert (tree / twin / "README.md").read_text(encoding="utf-8") == "new readme\n"
    assert (tree / twin / "LICENSE").read_bytes() == (tree / "LICENSE").read_bytes()


@pytest.mark.parametrize("snapshot_rel", SNAPSHOTS, ids=str)
def test_sync_preserves_the_executable_bit(tree: Path, snapshot_rel: Path) -> None:
    assert _sync(tree).returncode == 0
    script = tree / snapshot_rel / "scripts" / "wait-for-reviews.sh"
    assert script.stat().st_mode & 0o111
