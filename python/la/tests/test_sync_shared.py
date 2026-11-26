"""scripts/sync-shared on the real tree: --check writes nothing, a sync copies, removes and rehashes, root files stay."""

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
# Each package's root-file symlinks to the repo's README.md and LICENSE.
ROOT_LINKS = {Path("python/la/README.md"), Path("python/la/LICENSE"), Path("python/trmv/LICENSE")}


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """The real layout around sync-shared: snapshots, root files, the packages' symlinks to them, no `node/` copies."""
    for rel in ("scripts", "shared", *SNAPSHOTS):
        shutil.copytree(REPO_ROOT / rel, tmp_path / rel)
    for link in ROOT_LINKS:
        shutil.copy2(REPO_ROOT / link.name, tmp_path / link.name)
        (tmp_path / link).symlink_to(Path("..") / ".." / link.name)
    return tmp_path


def _sync(tree: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(tree / "scripts" / "sync-shared"), *args], capture_output=True, text=True, check=False
    )


def test_check_passes_on_a_synced_tree(tree: Path) -> None:
    assert _sync(tree, "--check").returncode == 0


@pytest.mark.parametrize("package", ["trmv", "la"])
def test_check_fails_after_shared_changes_and_writes_nothing(tree: Path, package: str) -> None:
    (tree / "shared" / package / "findings.yaml").write_text("changed\n", encoding="utf-8")
    proc = _sync(tree, "--check")
    assert proc.returncode == 1
    assert "scripts/sync-shared" in proc.stderr
    for snapshot in SNAPSHOTS:
        assert (tree / snapshot / "findings.yaml").read_text(encoding="utf-8") != "changed\n"


@pytest.mark.parametrize(("snapshot_rel", "package"), SNAPSHOTS.items(), ids=str)
def test_sync_copies_removes_and_rehashes(tree: Path, snapshot_rel: Path, package: str) -> None:
    (tree / "shared" / package / "new.yaml").write_text("x: 1\n", encoding="utf-8")
    (tree / "shared" / package / "README.md").unlink()
    assert _sync(tree).returncode == 0
    snapshot = tree / snapshot_rel
    assert (snapshot / "new.yaml").read_text(encoding="utf-8") == "x: 1\n"
    assert not (snapshot / "README.md").exists()
    assert (snapshot / "CONTRACT_HASH").read_text(encoding="utf-8") == compute_hash(tree / "shared" / package) + "\n"
    assert _sync(tree, "--check").returncode == 0


def test_sync_leaves_the_root_files_and_their_links_alone(tree: Path) -> None:
    names = sorted({link.name for link in ROOT_LINKS})
    before = {name: (tree / name).read_bytes() for name in names}
    assert _sync(tree, "--check").returncode == 0
    assert _sync(tree).returncode == 0
    for link in ROOT_LINKS:
        assert (tree / link).is_symlink(), link
        assert (tree / link).resolve() == (tree / link.name).resolve(), link
    for name in names:
        assert not list((tree / "node").glob(f"*/{name}")), name
        assert (tree / name).read_bytes() == before[name], name
