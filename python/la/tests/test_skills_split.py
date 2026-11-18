"""The two plugins: which skills each holds, the commands and skills they may name, and their preflights."""

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir())
PLUGINS = {package: REPO_ROOT / "plugin" / package for package in ("dr", "la")}
SKILLS = {package: sorted((root / "skills").glob("*/SKILL.md")) for package, root in PLUGINS.items()}
ALL_SKILLS = [(package, path) for package, paths in SKILLS.items() for path in paths]
DR_SKILLS = {"deterministic-refactor", "make-refactor-target-compliant", "make-diff-compliant", "init"}
LANGUAGE_IDS = list(yaml.safe_load((REPO_ROOT / "shared" / "dr" / "languages.yaml").read_text(encoding="utf-8")))
DR_CONFIG = Path(sys.executable).parent / "dr-config"
COMMAND_RE = re.compile(r"(?<![\w/.-])((?:la|dr)-[a-z][a-z-]*[a-z])\b")
SKILL_REF_RE = re.compile(r"\b(la|dr):([a-z][a-z-]*[a-z])\b")
CONFIG_GET_RE = re.compile(r"\b((?:la|dr)-config) get ([A-Za-z0-9_.<>-]*[A-Za-z0-9_>])")
PREFLIGHT = "{doctor} --plugin <this skill's base directory>"


def _id(item: tuple[str, Path]) -> str:
    return f"{item[0]}:{item[1].parent.name}"


def _manifest(package: str) -> set[str]:
    return set(yaml.safe_load((REPO_ROOT / "shared" / package / "cli.yaml").read_text(encoding="utf-8"))["commands"])


def _names(package: str) -> set[str]:
    return {path.parent.name for path in SKILLS[package]}


def test_dr_plugin_holds_exactly_the_dr_skills() -> None:
    assert _names("dr") == DR_SKILLS


def test_la_plugin_holds_none_of_the_moved_skills() -> None:
    assert _names("la") & (DR_SKILLS - {"init"}) == set()
    assert {"init", "pr", "arch-init", "arch-cleanup", "living-architecture"} <= _names("la")


@pytest.mark.parametrize("language", LANGUAGE_IDS)
def test_language_idioms_live_in_the_dr_plugin(language: str) -> None:
    assert (PLUGINS["dr"] / "languages" / f"{language}.md").is_file()
    assert not (PLUGINS["la"] / "languages").exists()


def test_the_single_plugin_directory_is_gone() -> None:
    assert sorted(p.name for p in (REPO_ROOT / "plugin").iterdir()) == ["dr", "la"]


@pytest.mark.parametrize("item", ALL_SKILLS, ids=_id)
def test_commands_exist_in_the_package_manifests(item: tuple[str, Path]) -> None:
    package, path = item
    allowed = _manifest("dr") | (_manifest("la") if package == "la" else set())
    used = set(COMMAND_RE.findall(path.read_text(encoding="utf-8")))
    assert used - allowed == set(), f"{package}:{path.parent.name} names {sorted(used - allowed)}"


@pytest.mark.parametrize("item", ALL_SKILLS, ids=_id)
def test_skill_references_resolve_in_their_plugin(item: tuple[str, Path]) -> None:
    package, path = item
    refs = set(SKILL_REF_RE.findall(path.read_text(encoding="utf-8")))
    if package == "dr":
        assert {ref for ref in refs if ref[0] == "la"} == set(), path.parent.name
    unresolved = {f"{p}:{name}" for p, name in refs if name not in _names(p)}
    assert unresolved == set()


@pytest.mark.parametrize("item", ALL_SKILLS, ids=_id)
def test_no_skill_names_the_deprecated_alias(item: tuple[str, Path]) -> None:
    assert "la-typecheck" not in item[1].read_text(encoding="utf-8")


@pytest.mark.parametrize("item", ALL_SKILLS, ids=_id)
def test_tool_users_run_their_plugins_preflight(item: tuple[str, Path]) -> None:
    package, path = item
    text = path.read_text(encoding="utf-8")
    doctor = f"{package}-doctor"
    if path.parent.name in {"pr-plan", "pr-tests", "pr-implement", "pr-review"}:
        return
    if set(COMMAND_RE.findall(text)) - {doctor}:
        assert f"`{PREFLIGHT.format(doctor=doctor)}" in text, f"{package}:{path.parent.name} lacks the {doctor} preflight"
    if package == "dr":
        assert "la-doctor" not in text


@pytest.mark.parametrize("item", [i for i in ALL_SKILLS if i[0] == "dr"], ids=_id)
def test_dr_skills_name_only_dr_config(item: tuple[str, Path]) -> None:
    assert {command for command, _ in CONFIG_GET_RE.findall(item[1].read_text(encoding="utf-8"))} <= {"dr-config"}


@pytest.fixture
def git_root(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    return tmp_path


def _invalid_keys(text: str, root: Path) -> list[str]:
    bad = []
    for command, key in sorted(set(CONFIG_GET_RE.findall(text))):
        executable = Path(sys.executable).parent / command
        concrete = [key.replace("<language>", lang) for lang in LANGUAGE_IDS] if "<language>" in key else [key]
        if any(subprocess.run([str(executable), "--root", str(root), "get", k], capture_output=True, check=False).returncode
               for k in concrete):
            bad.append(f"{command} get {key}")
    return bad


def test_dr_config_key_checker(git_root: Path) -> None:
    assert _invalid_keys("`dr-config get tracker`", git_root) == ["dr-config get tracker"]
    assert _invalid_keys("`dr-config get languages`, `dr-config get lang.<language>.markers`", git_root) == []
    assert _invalid_keys("`dr-config get commands.typecheck.<language>`, `dr-config get exempt`", git_root) == []


@pytest.mark.parametrize("item", ALL_SKILLS, ids=_id)
def test_config_keys_are_valid(item: tuple[str, Path], git_root: Path) -> None:
    assert _invalid_keys(item[1].read_text(encoding="utf-8"), git_root) == []


def test_dr_init_preflight_does_not_require_config() -> None:
    text = (PLUGINS["dr"] / "skills" / "init" / "SKILL.md").read_text(encoding="utf-8")
    preflight = re.findall(r"^\*\*Preflight:\*\*.*$", text, re.MULTILINE)
    assert len(preflight) == 1
    assert f"`{PREFLIGHT.format(doctor='dr-doctor')}`" in preflight[0]
    assert "--require-config" not in preflight[0]


def test_dr_config_is_on_the_python_twin_path() -> None:
    assert DR_CONFIG.is_file()
