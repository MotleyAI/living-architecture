"""`la-doctor`: check the installed tools match the plugin and the repo config is valid."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
from pathlib import Path

from living_architecture import __version__
from living_architecture.config import CONFIG_FILENAME, ConfigError, LaConfig, load_config, repo_languages
from living_architecture.contract import contract_hash, language, message

REQUIRED_EXECUTABLES = ("git", "gh")
PLUGIN_MANIFEST = Path(".claude-plugin") / "plugin.json"
_LONE_SURROGATE = re.compile("[\ud800-\udfff]")


def _version_problem(expected: str) -> str | None:
    if expected == __version__:
        return None
    return message("doctor.version-mismatch", installed=__version__, expected=expected)


def _reject_constant(name: str) -> None:
    raise ValueError(name)


def _is_file(path: Path) -> bool:
    """A missing entry is absent; other stat errors propagate."""
    try:
        return stat.S_ISREG(path.stat().st_mode)
    except (FileNotFoundError, NotADirectoryError):
        return False


def _manifest_problem(manifest: Path, raw: bytes) -> str | None:
    try:
        data = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
    except ValueError:
        data = None
    version = data.get("version") if isinstance(data, dict) else None
    if not isinstance(version, str) or _LONE_SURROGATE.search(version):
        return message("doctor.plugin-invalid", path=manifest)
    return _version_problem(version)


def _plugin_problem(plugin: str) -> str | None:
    """Check against the version in the nearest `.claude-plugin/plugin.json` at or above `plugin`."""
    # Collapse POSIX's leading `//` as Node's resolve() does.
    start = Path(re.sub(r"^//(?=[^/])", "/", os.path.abspath(plugin)))
    for directory in (start, *start.parents):
        manifest = directory / PLUGIN_MANIFEST
        try:
            if not _is_file(manifest):
                continue
            raw = manifest.read_bytes()
        except OSError:
            return message("doctor.plugin-unreadable", path=manifest)
        return _manifest_problem(manifest, raw)
    return message("doctor.plugin-not-found", dir=start)


def _consistency(root: Path, cfg: LaConfig) -> list[str]:
    """The config's gate decisions that the disk contradicts, in a fixed order."""
    problems: list[str] = []
    has_openspec = (root / "openspec").is_dir()
    has_architecture = _is_file(root / "architecture" / "index.yaml")
    if cfg.openspec != has_openspec:
        problems.append(message("doctor.openspec-absent" if cfg.openspec else "doctor.openspec-present"))
    if cfg.architecture != has_architecture:
        problems.append(message("doctor.architecture-absent" if cfg.architecture else "doctor.architecture-present"))
    if cfg.tracker == "none" and not cfg.openspec:
        problems.append(message("doctor.no-plan-store"))
    return problems


def _config_problems(root: Path, *, require_config: bool) -> list[str]:
    if not _is_file(root / CONFIG_FILENAME):
        return [message("doctor.config-missing")] if require_config else []
    try:
        cfg = load_config(root)
    except ConfigError as exc:
        return [str(exc)]
    return _consistency(root, cfg)


def _language_executables(root: Path) -> list[str]:
    """What the repo languages need on PATH; none outside git or with an invalid config."""
    if not (root / ".git").exists():
        return []
    try:
        cfg = load_config(root)
    except ConfigError:
        return []
    return [exe for lang_id in repo_languages(root, cfg) for exe in language(lang_id)["executables"]]


def run_checks(*, root: Path, expect: str | None, plugin: str | None = None, require_config: bool = False) -> list[str]:
    """Problems found; empty means healthy. Config-vs-disk checks run only when the config file exists."""
    versions = (
        _version_problem(expect) if expect is not None else None,
        _plugin_problem(plugin) if plugin is not None else None,
    )
    problems = [problem for problem in versions if problem is not None]
    problems += _config_problems(root, require_config=require_config)
    try:
        executables = [*REQUIRED_EXECUTABLES, *_language_executables(root)]
    except ConfigError as exc:
        problems.append(str(exc))
        executables = list(REQUIRED_EXECUTABLES)
    problems += [message("doctor.missing-executable", exe=exe) for exe in executables if shutil.which(exe) is None]
    return problems


def run(*, root: Path, expect: str | None, plugin: str | None, print_hash: bool, require_config: bool = False) -> int:
    if print_hash:
        print(contract_hash())
        return 0
    problems = run_checks(root=root, expect=expect, plugin=plugin, require_config=require_config)
    for problem in problems:
        print(message("doctor.fail", problem=problem))
    if not problems:
        source = CONFIG_FILENAME if (root / CONFIG_FILENAME).is_file() else message("doctor.no-config-file")
        print(message("doctor.ok", version=__version__, source=source))
    return 1 if problems else 0
