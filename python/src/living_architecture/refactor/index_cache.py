"""The occurrence-index cache: one entry per project root, outside the project, reused only while nothing the checker
reads has changed."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ValidationError

from living_architecture import __version__
from living_architecture.contract import language
from living_architecture.lang import (
    PYRIGHT_EXPORT_PRELOAD,
    PYRIGHT_PATCH_PRELOAD,
    ExportRequest,
    OccurrenceIndex,
)
from living_architecture.refactor.routing import language_files, stub_files

_FORMAT = 1
_CONFIGS = ("pyrightconfig.json", "pyproject.toml")
_SEARCH_PATHS = (
    "import json, os, sys; cwd = os.path.normcase(os.path.normpath(os.getcwd())); "
    "json.dump(dict(executable=sys.executable, version=list(sys.version_info), prefix=sys.prefix, "
    "path=[p for p in sys.path if p and os.path.normcase(os.path.normpath(p)) != cwd]), sys.stdout)"
)


class CacheEntry(BaseModel):
    """A project root's cached exports: the fingerprint they hold for, and each export by its request's hash."""

    format: int = _FORMAT
    fingerprint: str
    exports: dict[str, OccurrenceIndex]


def cache_dir() -> Path:
    """`LA_CACHE_DIR`, else the user's cache directory."""
    configured = os.environ.get(language("python")["cache_dir_variable"])
    if configured:
        return Path(configured)
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "living-architecture" / "Cache"
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "living-architecture"


def request_key(request: ExportRequest, texts: dict[Path, str]) -> str:
    """The hash of an export request and of the texts its files are opened with, where they differ from disk."""
    payload = {"request": request.model_dump(mode="json"), "texts": {str(p): t for p, t in sorted(texts.items())}}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _tree(directory: Path, project: Path, digest: Any) -> None:
    """Every file under `directory`, the project root itself aside (its sources are hashed): path, size, mtime."""
    if not directory.is_dir() or directory.resolve() == project:
        return
    for top, dirs, files in os.walk(directory):
        dirs.sort()
        for name in sorted(files):
            path = os.path.join(top, name)
            with contextlib.suppress(OSError):
                stat = os.stat(path)
                digest.update(f"{path}\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode(errors="surrogateescape"))


def _config_venv(root: Path) -> Path | None:
    """The environment the project's checker configuration names (`venvPath` and `venv`)."""
    found: dict[str, Any] = {}
    with contextlib.suppress(OSError, ValueError):
        found = cast(dict[str, Any], json.loads((root / "pyrightconfig.json").read_text(encoding="utf-8")))
    if not found:
        with contextlib.suppress(OSError, ValueError):
            tool = cast(dict[str, Any], tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8")).get("tool", {}))
            found = cast(dict[str, Any], tool.get("basedpyright") or tool.get("pyright") or {})
    venv_path, venv = found.get("venvPath"), found.get("venv")
    if not isinstance(venv_path, str) or not isinstance(venv, str):
        return None
    return (root / venv_path / venv).resolve()


def _interpreter(digest: Any, project: Path) -> None:
    """The interpreter basedpyright falls back on and every search path it reports."""
    found = shutil.which("python3") if sys.platform != "win32" else None
    found = found or shutil.which("python")
    if found is None:
        digest.update(b"no interpreter\n")
        return
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    with tempfile.TemporaryDirectory(prefix="la-cache-") as cwd:
        try:
            out = subprocess.run([found, "-I", "-c", _SEARCH_PATHS], cwd=cwd, env=env, capture_output=True, text=True,
                                 timeout=60, check=True).stdout
            info = cast(dict[str, Any], json.loads(out))
        except (OSError, subprocess.SubprocessError, ValueError):
            digest.update(f"interpreter {found} failed\n".encode())
            return
    digest.update(json.dumps(info, sort_keys=True).encode())
    for entry in cast(list[str], info.get("path", [])):
        _tree(Path(entry), project, digest)


def fingerprint(root: Path) -> str:
    """Everything the export reads besides the request: la and basedpyright, the project's sources and checker
    configuration, and the environment the checker resolves imports in."""
    digest = hashlib.sha256()
    digest.update(f"{_FORMAT} {__version__} {importlib.metadata.version('basedpyright')}\n".encode())
    for preload in (PYRIGHT_EXPORT_PRELOAD, PYRIGHT_PATCH_PRELOAD):
        digest.update(hashlib.sha256(preload.read_bytes()).digest())
    sources = {*language_files(root, "python"), *stub_files(root, "python", ".pyi")}
    for path in sorted(sources):
        with contextlib.suppress(OSError):
            digest.update(f"{path.relative_to(root).as_posix()}\0".encode(errors="surrogateescape"))
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    for name in _CONFIGS:
        with contextlib.suppress(OSError):
            digest.update(f"{name}\0".encode())
            digest.update(hashlib.sha256((root / name).read_bytes()).digest())
    venv = _config_venv(root)
    if venv is not None and venv.is_dir():
        digest.update(f"venv {venv}\n".encode())
        _tree(venv, root, digest)
    else:
        _interpreter(digest, root)
    return digest.hexdigest()


class IndexCache:
    """The cache entry of project `root`: read once, extended by the run's exports, written atomically."""

    def __init__(self, root: Path) -> None:
        self.root = root
        name = hashlib.sha256(str(root).encode(errors="surrogateescape")).hexdigest()[:32]
        self.path = cache_dir() / "occurrences" / f"{name}.json"
        self._fingerprint: str | None = None
        self._stored: dict[str, OccurrenceIndex] | None = None
        self._run: dict[str, OccurrenceIndex] = {}

    def _current(self) -> str:
        if self._fingerprint is None:
            self._fingerprint = fingerprint(self.root)
        return self._fingerprint

    def _entries(self) -> dict[str, OccurrenceIndex]:
        if self._stored is None:
            self._stored = {}
            try:
                entry = CacheEntry.model_validate_json(self.path.read_bytes())
            except (OSError, ValueError, ValidationError):
                return self._stored
            if entry.format == _FORMAT and entry.fingerprint == self._current():
                self._stored = entry.exports
        return self._stored

    def get(self, key: str) -> OccurrenceIndex | None:
        found = self._run.get(key) or self._entries().get(key)
        if found is not None:
            self._run[key] = found
        return found

    def put(self, key: str, index: OccurrenceIndex) -> None:
        self._run[key] = index

    def save(self) -> None:
        """Replace the entry with this run's exports; a cache that cannot be written is skipped."""
        if not self._run or self._run == self._entries():
            return
        entry = CacheEntry(fingerprint=self._current(), exports=self._run)
        with contextlib.suppress(OSError):
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".entry-", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(entry.model_dump_json())
                os.replace(tmp, self.path)
            finally:
                with contextlib.suppress(OSError):
                    os.unlink(tmp)
