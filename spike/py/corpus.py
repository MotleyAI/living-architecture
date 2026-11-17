"""The spike's input corpora: their `.py` files and a manifest hash that pins them."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

SPIKE = Path(__file__).resolve().parent.parent
REPO = SPIKE.parent
DATA = SPIKE / "tests" / "data"
CONFORMANCE = REPO / "conformance"
SLAYER_MANIFEST = SPIKE / "slayer-manifest.sha256"


def py_files(root: Path) -> list[str]:
    """Every `.py` file under `root`, root-relative and sorted; symlinked directories are not followed."""
    found: list[str] = []
    for folder, _, names in os.walk(root):
        found += [Path(folder, n).relative_to(root).as_posix() for n in names if n.endswith(".py")]
    return sorted(found)


def manifest_hash(root: Path) -> str:
    """A sha256 over each `.py` file's relative path and content hash, in sorted order."""
    digest = hashlib.sha256()
    for rel in py_files(root):
        digest.update(f"{rel}\0{hashlib.sha256((root / rel).read_bytes()).hexdigest()}\n".encode())
    return digest.hexdigest()


class ManifestMismatch(Exception):
    """The corpus differs from the one its recorded manifest hash pins."""


def check_manifest(root: Path, recorded: Path = SLAYER_MANIFEST) -> None:
    """Raises `ManifestMismatch` unless `root`'s manifest hash equals the one recorded in `recorded`."""
    expected = recorded.read_text(encoding="utf-8").strip()
    actual = manifest_hash(root)
    if actual != expected:
        raise ManifestMismatch(f"{root}: manifest {actual} differs from the recorded {expected}")
