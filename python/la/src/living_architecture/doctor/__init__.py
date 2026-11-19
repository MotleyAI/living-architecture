"""`la-doctor`: check the installed tools match the plugin's minor series and the repo config is valid."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from deterministic_refactor import twin
from deterministic_refactor.config import ConfigError, both_files_problem, check_format, repo_languages
from deterministic_refactor.contract import is_regular_file, language, os_error_text, plugin_problem
from living_architecture import NATIVE_LANGUAGE, __version__
from living_architecture.config import LaConfig, languages_of, load_config, load_raw, resolve_raw
from living_architecture.contract import LA, config_file, contract_hash, identity, local_config_file, message

REQUIRED_EXECUTABLES = ("git", "gh")


def _plugin_name() -> str:
    return LA.yaml("cli.yaml")["plugin"]


def _install(version: str) -> str:
    return twin.install_command(NATIVE_LANGUAGE, identity(), version)


def _dr_problem() -> str | None:
    """The first `dr-doctor` on PATH missing, or reporting another language, version or dr contract than la runs with."""
    expected = twin.dr_identity().model_copy(update={"version": __version__}).line(NATIVE_LANGUAGE)
    found = shutil.which(twin.dr_identity().doctor)
    if found is None:
        return message("doctor.dr-missing", install=_install(__version__))
    try:
        proc = subprocess.run([found, "--twin"], capture_output=True, check=False)
        reported = proc.stdout.decode("utf-8", "replace").strip() if proc.returncode == 0 else ""
    except OSError:
        reported = ""
    if reported == expected:
        return None
    install = _install(__version__)
    return message("doctor.dr-mismatch", reported=reported, version=__version__, expected=expected, install=install)


def _consistency(root: Path, cfg: LaConfig, *, require_plan_store: bool) -> list[str]:
    """The config's gate decisions that the disk contradicts, in a fixed order."""
    problems: list[str] = []
    has_openspec = (root / "openspec").is_dir()
    if cfg.openspec != has_openspec:
        problems.append(message("doctor.openspec-absent" if cfg.openspec else "doctor.openspec-present"))
    try:
        has_architecture = is_regular_file(root / "architecture" / "index.yaml")
    except OSError as exc:
        problems.append(os_error_text(exc, root))
    else:
        if cfg.architecture != has_architecture:
            problems.append(message("doctor.architecture-absent" if cfg.architecture else "doctor.architecture-present"))
    if require_plan_store and cfg.tracker == "none" and not cfg.openspec:
        problems.append(message("doctor.no-plan-store"))
    return problems


def _config_problems(root: Path, *, require_config: bool, require_plan_store: bool) -> list[str]:
    try:
        has_committed = is_regular_file(root / config_file())
        has_local = is_regular_file(root / local_config_file())
    except OSError as exc:
        return [os_error_text(exc, root)]
    missing = [message("doctor.config-missing")] if require_config and not has_committed else []
    if not has_committed and not has_local:
        return missing
    try:
        cfg = load_config(root)
    except ConfigError as exc:
        return [*missing, str(exc)]
    return _consistency(root, cfg, require_plan_store=require_plan_store) if has_committed else missing


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
    dr = _dr_problem()
    if dr is not None:
        problems.append(dr)
    refusal = both_files_problem(root) or check_format(root, config_file())
    if refusal is not None:
        problems.append(refusal)
    else:
        problems += _config_problems(root, require_config=require_config, require_plan_store=require_plan_store)
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
        source = config_file() if (root / config_file()).is_file() else message("doctor.no-config-file")
        if (root / local_config_file()).is_file():
            source = message("doctor.local-source", source=source, local=local_config_file())
        print(message("doctor.ok", package=_plugin_name(), version=__version__, source=source))
    return 1 if problems else 0
