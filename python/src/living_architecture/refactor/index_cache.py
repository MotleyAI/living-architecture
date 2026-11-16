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


Config = tuple[Path, dict[str, Any]]


def _jsonc(text: str) -> str:
    """JSON with comments and trailing commas, as Pyright reads its configuration, as plain JSON."""
    out: list[str] = []
    comma = False
    i, n = 0, len(text)
    while i < n:
        char = text[i]
        if text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        if char.isspace():
            out.append(char)
            i += 1
            continue
        if comma and char not in "}]":
            out.append(",")
        comma = char == ","
        if comma:
            i += 1
            continue
        end = i + 1
        if char == '"':
            while end < n and text[end] != '"':
                end += 2 if text[end] == "\\" else 1
            end += 1
        out.append(text[i:end])
        i = end
    return "".join(out)


def _read_config(path: Path) -> dict[str, Any]:
    found: Any = {}
    with contextlib.suppress(OSError, ValueError):
        if path.suffix == ".toml":
            tool = cast(dict[str, Any], tomllib.loads(path.read_text(encoding="utf-8-sig")).get("tool", {}))
            found = tool.get("basedpyright") or tool.get("pyright") or {}
        else:
            found = json.loads(_jsonc(path.read_text(encoding="utf-8-sig")))
    return cast(dict[str, Any], found) if isinstance(found, dict) else {}


def _config_chain(root: Path) -> list[Config]:
    """The project's checker configuration file and each file it `extends`, child first."""
    path = root / "pyrightconfig.json"
    if not path.is_file():
        path = root / "pyproject.toml"
    chain: list[Config] = []
    seen: set[Path] = set()
    while path.resolve() not in seen:
        seen.add(path.resolve())
        config = _read_config(path)
        chain.append((path, config))
        extends = config.get("extends")
        if not isinstance(extends, str):
            break
        path = path.parent / extends
    return chain


def _config_venv(chain: list[Config]) -> Path | None:
    """The environment the configuration names (`venvPath` and `venv`), each from the nearest file setting it."""
    venv_path = next(((p.parent / c["venvPath"]) for p, c in chain if isinstance(c.get("venvPath"), str)), None)
    venv = next((c["venv"] for _, c in chain if isinstance(c.get("venv"), str)), None)
    if venv_path is None or venv is None:
        return None
    return (venv_path / venv).resolve()


def _config_dirs(chain: list[Config]) -> list[Path]:
    """The further directories any file of the configuration resolves imports in: `extraPaths` (also per execution
    environment), `stubPath` and `typeshedPath`."""
    out: set[Path] = set()
    for path, config in chain:
        found: list[Any] = [config.get("stubPath"), config.get("typeshedPath"), *(config.get("extraPaths") or [])]
        for env in config.get("executionEnvironments") or []:
            if isinstance(env, dict):
                found += cast(dict[str, Any], env).get("extraPaths") or []
        out |= {(path.parent / d).resolve() for d in found if isinstance(d, str)}
    return sorted(out)


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
    configuration, and the directories and environment the checker resolves imports in."""
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
    chain = _config_chain(root)
    for path, _ in chain[1:]:
        digest.update(f"extends {path}\0".encode(errors="surrogateescape"))
        with contextlib.suppress(OSError):
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    for directory in _config_dirs(chain):
        digest.update(f"dir {directory}\n".encode(errors="surrogateescape"))
        _tree(directory, root, digest)
    venv = _config_venv(chain)
    if venv is not None and venv.is_dir():
        digest.update(f"venv {venv}\n".encode())
        _tree(venv, root, digest)
    else:
        _interpreter(digest, root)
    return digest.hexdigest()


class IndexCache:
    """The cache entry of project `root`: read once, extended by the run's exports, written atomically only while its
    fingerprint, taken before any export, still holds. A cache directory inside the project means no cache."""

    def __init__(self, root: Path) -> None:
        self.root = root
        name = hashlib.sha256(str(root).encode(errors="surrogateescape")).hexdigest()[:32]
        directory = cache_dir()
        inside = directory.resolve().is_relative_to(root.resolve())
        self.path: Path | None = None if inside else directory / "occurrences" / f"{name}.json"
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
            if self.path is None:
                return self._stored
            current = self._current()
            try:
                entry = CacheEntry.model_validate_json(self.path.read_bytes())
            except (OSError, ValueError, ValidationError):
                return self._stored
            if entry.format == _FORMAT and entry.fingerprint == current:
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
        if self.path is None or not self._run or self._run == self._entries():
            return
        if fingerprint(self.root) != self._current():
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
