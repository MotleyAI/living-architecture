"""The contract hash: sha256 over (POSIX path, executable bit, length, bytes) of every file but the hash file."""

from __future__ import annotations

import hashlib
from pathlib import Path

HASH_FILE = "CONTRACT_HASH"


def contract_files(root: Path) -> list[Path]:
    return sorted(
        (p for p in root.rglob("*") if p.is_file() and p.name != HASH_FILE),
        key=lambda p: p.relative_to(root).as_posix().encode("utf-8"),
    )


def compute_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in contract_files(root):
        data = path.read_bytes()
        executable = b"1" if path.stat().st_mode & 0o111 else b"0"
        rel = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(b"\0".join([rel, executable, str(len(data)).encode("ascii"), data]))
    return digest.hexdigest()
