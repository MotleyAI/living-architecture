"""The vendored contract snapshot: its location, hash and data files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from trmv.contract.glob import glob_match
from trmv.contract.yaml_profile import load_yaml

HASH_FILE = "CONTRACT_HASH"


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


class Snapshot:
    """A vendored contract directory: its recorded hash and its data files."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._yaml: dict[str, Any] = {}
        self._schemas: dict[str, dict[str, Any]] = {}

    def contract_hash(self) -> str:
        """The hash recorded when the snapshot was vendored."""
        return (self.root / HASH_FILE).read_text(encoding="utf-8").strip()

    def yaml(self, name: str) -> Any:
        if name not in self._yaml:
            self._yaml[name] = load_yaml((self.root / name).read_text(encoding="utf-8"))
        return self._yaml[name]

    def schema(self, name: str) -> dict[str, Any]:
        if name not in self._schemas:
            path = self.root / "schema" / f"{name}.schema.json"
            self._schemas[name] = json.loads(path.read_text(encoding="utf-8"))
        return self._schemas[name]

    def schema_names(self) -> list[str]:
        """Every schema's name, as `schema` takes it."""
        return sorted(p.name.removesuffix(".schema.json") for p in (self.root / "schema").glob("*.schema.json"))

    def findings(self) -> dict[str, str]:
        return self.yaml("findings.yaml")["findings"]

    def manifest(self) -> dict[str, Any]:
        return self.yaml("cli.yaml")["commands"]

    def script_path(self, name: str) -> Path:
        return self.root / "scripts" / name


TRMV = Snapshot(Path(__file__).resolve().parent / "data")


def snapshot_dir() -> Path:
    return TRMV.root


def contract_hash() -> str:
    """The hash recorded when trmv's snapshot was vendored."""
    return TRMV.contract_hash()


def schema(name: str) -> dict[str, Any]:
    return TRMV.schema(name)


def schema_names() -> list[str]:
    """Every trmv schema's name, as `schema` takes it."""
    return TRMV.schema_names()


def findings() -> dict[str, str]:
    return TRMV.findings()


def manifest() -> dict[str, Any]:
    return TRMV.manifest()


def _cli() -> Any:
    return TRMV.yaml("cli.yaml")


def base_fetch_timeout() -> float:
    """Seconds after which the best-effort fetch of a base branch is killed."""
    return float(_cli()["base_fetch_timeout_seconds"])


def literal_value_forbidden() -> tuple[str, ...]:
    """The substrings a `Literal` member's new value may not hold."""
    return tuple(_cli()["literal_value_forbidden"])


def timing_phases() -> tuple[str, ...]:
    """The phases `trmv-refactor --timings` reports, in print order."""
    return tuple(_cli()["timing_phases"])


def language_keys() -> list[str]:
    """The public `lang.<language>.<key>` keys."""
    return list(_cli()["language_keys"])


def language(name: str) -> dict[str, Any]:
    return TRMV.yaml("languages.yaml")[name]


def language_ids() -> list[str]:
    """Every language of the registry, in id order."""
    return sorted(TRMV.yaml("languages.yaml"))


def language_of(path: str) -> str | None:
    """The registry language whose source extensions contain the path's extension, else None."""
    for lang_id in language_ids():
        if any(path.endswith(ext) for ext in language(lang_id)["source_extensions"]):
            return lang_id
    return None


def is_test_file(path: str) -> bool:
    """The path has a registry language's source extension and matches that language's test globs."""
    lang_id = language_of(path)
    return lang_id is not None and any(glob_match(g, path) for g in language(lang_id)["test_globs"])


def config_files() -> list[str]:
    """The committed config files a trmv command reads, in order: the first present at the repo root."""
    return list(TRMV.yaml("config.yaml")["files"])


def config_formats(file: str) -> list[str]:
    """Every released format of config file `file`, oldest first."""
    return list(TRMV.yaml("config.yaml")["formats"][file])


def stealth_files() -> list[tuple[str, str]]:
    """Each package's stealth config file, relative to the git common directory, in lookup order."""
    return [(entry["package"], entry["path"]) for entry in TRMV.yaml("config.yaml")["stealth_files"]]


def stealth_registry() -> list[str]:
    """trmv's stealth path registry: repo-relative paths that must not show in a stealth repo."""
    return list(TRMV.yaml("config.yaml")["stealth_registry"])
