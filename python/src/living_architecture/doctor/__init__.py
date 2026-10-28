"""`la-doctor`: check the installed tools match the plugin's minor series and the repo config is valid."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

from living_architecture import NATIVE_LANGUAGE, __version__
from living_architecture.config import ConfigError, LaConfig, check_format, load_config, repo_languages
from living_architecture.contract import (
    config_file,
    contract_hash,
    language,
    local_config_file,
    message,
    render_template,
)

REQUIRED_EXECUTABLES = ("git", "gh")
PLUGIN_MANIFEST = Path(".claude-plugin") / "plugin.json"
_LONE_SURROGATE = re.compile("[\ud800-\udfff]")
_VERSION_FORM = re.compile(r"([0-9]+)\.([0-9]+)\..+", re.DOTALL)


def _series(version: str) -> tuple[str, str] | None:
    """Major and minor of `<digits>.<digits>.<rest>` as written, or None."""
    match = _VERSION_FORM.fullmatch(version)
    return (match[1], match[2]) if match else None


def _canonical(series: tuple[str, str]) -> tuple[str, ...]:
    return tuple(part.lstrip("0") or "0" for part in series)


def _version_problem(expected: str, series: tuple[str, str]) -> str | None:
    installed = _series(__version__)
    if installed is not None and _canonical(installed) == _canonical(series):
        return None
    install = render_template(language(NATIVE_LANGUAGE)["install"], {"version": expected})
    return message(
        "doctor.version-mismatch", installed=__version__, expected=expected, series=".".join(series), install=install
    )


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
    if not isinstance(version, str) or _LONE_SURROGATE.search(version) or (series := _series(version)) is None:
        return message("doctor.plugin-invalid", path=manifest)
    return _version_problem(version, series)


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
    has_committed = _is_file(root / config_file())
    missing = [message("doctor.config-missing")] if require_config and not has_committed else []
    if not has_committed and not _is_file(root / local_config_file()):
        return missing
    try:
        cfg = load_config(root)
    except ConfigError as exc:
        return [*missing, str(exc)]
    return _consistency(root, cfg) if has_committed else missing


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes] | None:
    """A quiet git run, or None when git cannot start."""
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, check=False)
    except OSError:
        return None


def _local_problem(root: Path) -> str | None:
    """A local file that git tracks or does not ignore; checked only inside git."""
    local = local_config_file()
    if not (root / ".git").exists() or not _is_file(root / local):
        return None
    listed = _git(root, "ls-files", "-z", "--", local)
    if listed is None or listed.returncode != 0:
        return message("doctor.local-git-failed", file=local)
    if listed.stdout:
        return message("doctor.local-tracked", file=local)
    ignored = _git(root, "check-ignore", "-q", "--", local)
    status = None if ignored is None else ignored.returncode
    if status == 1:
        return message("doctor.local-not-ignored", file=local)
    return None if status == 0 else message("doctor.local-git-failed", file=local)


def _language_executables(root: Path) -> list[str]:
    """What the repo languages need on PATH; none outside git or with an invalid config."""
    if not (root / ".git").exists():
        return []
    try:
        cfg = load_config(root)
    except ConfigError:
        return []
    return [exe for lang_id in repo_languages(root, cfg) for exe in language(lang_id)["executables"]]


def run_checks(*, root: Path, plugin: str | None = None, require_config: bool = False) -> list[str]:
    """Problems found; empty means healthy. A format refusal replaces every check that reads the config."""
    version = _plugin_problem(plugin) if plugin is not None else None
    problems = [version] if version is not None else []
    refusal = check_format(root)
    problems += [refusal] if refusal is not None else _config_problems(root, require_config=require_config)
    local = _local_problem(root)
    if local is not None:
        problems.append(local)
    executables = list(REQUIRED_EXECUTABLES)
    try:
        if refusal is None:
            executables += _language_executables(root)
    except ConfigError as exc:
        problems.append(str(exc))
    problems += [message("doctor.missing-executable", exe=exe) for exe in executables if shutil.which(exe) is None]
    return problems


def run(*, root: Path, plugin: str | None, print_hash: bool, require_config: bool = False) -> int:
    if print_hash:
        print(contract_hash())
        return 0
    problems = run_checks(root=root, plugin=plugin, require_config=require_config)
    for problem in problems:
        print(message("doctor.fail", problem=problem))
    if not problems:
        source = config_file() if (root / config_file()).is_file() else message("doctor.no-config-file")
        if (root / local_config_file()).is_file():
            source = message("doctor.local-source", source=source, local=local_config_file())
        print(message("doctor.ok", version=__version__, source=source))
    return 1 if problems else 0
