"""`la-doctor`: check the installed tools match the plugin's minor series and the repo config is valid."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from living_architecture import NATIVE_LANGUAGE, __version__
from living_architecture.config import (
    LaConfig,
    RawConfig,
    languages_of,
    load_raw,
    openspec_store_id,
    private_store,
    resolve_raw,
    tracks_openspec,
)
from living_architecture.contract import (
    LA,
    contract_hash,
    identity,
    local_config_file,
    message,
    stealth_path,
    stealth_registry,
)
from trmv import twin
from trmv.config import (
    ConfigError,
    check_format,
    config_source,
    files_problem,
    repo_languages,
    stray_findings,
    trmv_stray_findings,
)
from trmv.contract import is_regular_file, language, os_error_text, plugin_problem
from trmv.contract import stealth_registry as trmv_registry

REQUIRED_EXECUTABLES = ("git", "gh")


def _plugin_name() -> str:
    return LA.yaml("cli.yaml")["plugin"]


def _install(version: str) -> str:
    return twin.install_command(NATIVE_LANGUAGE, identity(), version)


def _dr_problem() -> str | None:
    """The first `trmv-doctor` on PATH missing, or reporting another language, version or trmv contract than la runs with."""
    expected = twin.trmv_identity().model_copy(update={"version": __version__}).line(NATIVE_LANGUAGE)
    found = shutil.which(twin.trmv_identity().doctor)
    if found is None:
        return message("doctor.trmv-missing", install=_install(__version__))
    try:
        proc = subprocess.run([found, "--twin"], capture_output=True, check=False)
        reported = proc.stdout.decode("utf-8", "replace").strip() if proc.returncode == 0 else ""
    except OSError:
        reported = ""
    if reported == expected:
        return None
    install = _install(__version__)
    return message("doctor.trmv-mismatch", reported=reported, version=__version__, expected=expected, install=install)


def _store_registered(store_id: str) -> bool:
    """Whether the OpenSpec CLI lists `store_id` among its registered stores."""
    try:
        proc = subprocess.run(["openspec", "store", "list", "--json"], capture_output=True, check=False)
        stores = json.loads(proc.stdout).get("stores", []) if proc.returncode == 0 else []
    except (OSError, ValueError, AttributeError):
        return False
    return any(isinstance(s, dict) and s.get("id") == store_id for s in stores)


def _openspec_problem(root: Path, cfg: LaConfig, raw: RawConfig) -> str | None:
    store = private_store(root, cfg, raw)
    if store is not None:
        store_id = openspec_store_id(store)
        ready = (store / stealth_path("openspec_store")).is_dir() and _store_registered(store_id)
        return None if ready else message("doctor.private-store-missing", id=store_id)
    if raw.source is not None and raw.source.stealth and not cfg.openspec:
        return None
    has_openspec = (root / "openspec").is_dir()
    if cfg.openspec != has_openspec:
        return message("doctor.openspec-absent" if cfg.openspec else "doctor.openspec-present")
    return None


def _consistency(root: Path, cfg: LaConfig, raw: RawConfig, *, require_plan_store: bool) -> list[str]:
    """The config's gate decisions that the disk contradicts, in a fixed order."""
    problems: list[str] = []
    openspec = _openspec_problem(root, cfg, raw)
    if openspec is not None:
        problems.append(openspec)
    try:
        has_architecture = is_regular_file(root / "architecture" / "index.yaml")
    except OSError as exc:
        problems.append(os_error_text(exc, root))
    else:
        if cfg.architecture != has_architecture:
            problems.append(message("doctor.architecture-absent" if cfg.architecture else "doctor.architecture-present"))
    stealth = raw.source is not None and raw.source.stealth
    if require_plan_store and cfg.tracker == "none" and not cfg.openspec and not stealth:
        problems.append(message("doctor.no-plan-store"))
    return problems


def _config_problems(root: Path, *, require_config: bool, require_plan_store: bool) -> list[str]:
    try:
        has_local = is_regular_file(root / local_config_file())
        raw = load_raw(root)
    except OSError as exc:
        return [os_error_text(exc, root)]
    except ConfigError as exc:
        missing = [message("doctor.config-missing")] if require_config and config_source(root, "la") is None else []
        return [*missing, str(exc)]
    missing = [message("doctor.config-missing")] if require_config and raw.source is None else []
    if raw.source is None and not has_local:
        return missing
    try:
        cfg = resolve_raw(root, raw)
    except ConfigError as exc:
        return [*missing, str(exc)]
    return _consistency(root, cfg, raw, require_plan_store=require_plan_store) if raw.source is not None else missing


def _registry_problems(root: Path) -> list[str]:
    """In a stealth repo, la's and trmv's registry paths that show in the working tree."""
    trmv = trmv_stray_findings(root)
    if not (root / ".git").exists():
        return trmv
    try:
        raw = load_raw(root)
    except ConfigError:
        raw = None
    if raw is None or raw.source is None or not raw.source.stealth:
        return trmv
    paths, prefix = stealth_registry()
    prefixes = [] if tracks_openspec(root) else [prefix]
    try:
        own = stray_findings(root, [p for p in paths if p not in trmv_registry()], prefixes)
    except ConfigError as exc:
        own = [str(exc)]
    return [*own, *trmv]


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes] | None:
    """A quiet git run, or None when git cannot start."""
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, check=False)
    except OSError:
        return None


def _local_problem(root: Path) -> str | None:
    """A local file that git tracks or does not ignore; checked only inside git."""
    local = local_config_file()
    try:
        if not (root / ".git").exists() or not is_regular_file(root / local):
            return None
    except OSError:  # reported by the config checks
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
        raw = load_raw(root)
        settings = languages_of(resolve_raw(root, raw), raw)
    except ConfigError:
        return []
    return [exe for lang_id in repo_languages(root, settings) for exe in language(lang_id)["executables"]]


def run_checks(
    *, root: Path, plugin: str | None = None, require_config: bool = False, require_plan_store: bool = False
) -> list[str]:
    """Problems found; empty means healthy. Both config files present, or a format refusal, replace every check that
    reads the config."""
    problems: list[str] = []
    if plugin is not None and (version := plugin_problem(plugin, _plugin_name(), __version__, _install)) is not None:
        problems.append(version)
    trmv = _dr_problem()
    if trmv is not None:
        problems.append(trmv)
    refusal = files_problem(root) or check_format(root, "la")
    if refusal is not None:
        problems.append(refusal)
    else:
        problems += _config_problems(root, require_config=require_config, require_plan_store=require_plan_store)
    problems += _registry_problems(root)
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


def run(
    *, root: Path, plugin: str | None, print_hash: bool, require_config: bool = False, require_plan_store: bool = False
) -> int:
    if print_hash:
        print(contract_hash())
        return 0
    problems = run_checks(
        root=root, plugin=plugin, require_config=require_config, require_plan_store=require_plan_store
    )
    for problem in problems:
        print(message("doctor.fail", problem=problem))
    if not problems:
        source = config_source(root, "la") or message("doctor.no-config-file")
        if (root / local_config_file()).is_file():
            source = message("doctor.local-source", source=source, local=local_config_file())
        print(message("doctor.ok", package=_plugin_name(), version=__version__, source=source))
    return 1 if problems else 0
