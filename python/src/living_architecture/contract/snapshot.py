"""The vendored contract snapshot: its location, hash and data files."""

from __future__ import annotations

import hashlib
import json
from functools import cache
from pathlib import Path
from typing import Any

from living_architecture.contract.yaml_profile import load_yaml

HASH_FILE = "CONTRACT_HASH"


def snapshot_dir() -> Path:
    return Path(__file__).resolve().parent / "data"


def _files(root: Path) -> list[Path]:
    return sorted(
        (p for p in root.rglob("*") if p.is_file() and p.name != HASH_FILE),
        key=lambda p: p.relative_to(root).as_posix().encode("utf-8"),
    )


def compute_hash(root: Path) -> str:
    """sha256 over (POSIX path, executable bit, length, bytes) of every file but the hash file."""
    digest = hashlib.sha256()
    for path in _files(root):
        data = path.read_bytes()
        executable = b"1" if path.stat().st_mode & 0o111 else b"0"
        rel = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(b"\0".join([rel, executable, str(len(data)).encode("ascii"), data]))
    return digest.hexdigest()


def contract_hash() -> str:
    """The hash recorded when the snapshot was vendored."""
    return (snapshot_dir() / HASH_FILE).read_text(encoding="utf-8").strip()


@cache
def _yaml(name: str) -> Any:
    return load_yaml((snapshot_dir() / name).read_text(encoding="utf-8"))


@cache
def schema(name: str) -> dict[str, Any]:
    return json.loads((snapshot_dir() / "schema" / f"{name}.schema.json").read_text(encoding="utf-8"))


def findings() -> dict[str, str]:
    return _yaml("findings.yaml")["findings"]


def check_ids() -> frozenset[str]:
    return frozenset(_yaml("findings.yaml")["check_ids"])


def manifest() -> dict[str, Any]:
    return _yaml("cli.yaml")["commands"]


def language(name: str) -> dict[str, Any]:
    return _yaml("languages.yaml")[name]


def conventions() -> dict[str, Any]:
    return _yaml("conventions.yaml")


def script_path(name: str) -> Path:
    return snapshot_dir() / "scripts" / name
