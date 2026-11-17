"""Corpus listing and the manifest hash that pins the SLayer copy."""

from __future__ import annotations

from pathlib import Path

import pytest
from corpus import ManifestMismatch, check_manifest, manifest_hash, py_files


def test_py_files_sorted_relative_and_skips_symlinked_dirs(tmp_path: Path) -> None:
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "z.py").write_text("")
    (tmp_path / "a.py").write_text("")
    (tmp_path / "notes.txt").write_text("")
    outside = tmp_path.parent / f"{tmp_path.name}-venv"
    outside.mkdir()
    (outside / "dep.py").write_text("")
    (tmp_path / ".venv").symlink_to(outside)
    assert py_files(tmp_path) == ["a.py", "b/z.py"]


def test_manifest_hash_follows_paths_and_contents(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    first = manifest_hash(tmp_path)
    assert manifest_hash(tmp_path) == first
    (tmp_path / "a.py").write_text("x = 2\n")
    assert manifest_hash(tmp_path) != first


def test_check_manifest_refuses_a_changed_corpus(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    recorded = tmp_path / "manifest"
    recorded.write_text(manifest_hash(tmp_path) + "\n")
    check_manifest(tmp_path, recorded)
    (tmp_path / "b.py").write_text("")
    with pytest.raises(ManifestMismatch):
        check_manifest(tmp_path, recorded)


@pytest.mark.slayer
def test_slayer_copy_matches_its_recorded_manifest(request: pytest.FixtureRequest) -> None:
    root = request.config.getoption("--slayer")
    if root is None:
        pytest.skip("no --slayer")
    check_manifest(Path(root))
