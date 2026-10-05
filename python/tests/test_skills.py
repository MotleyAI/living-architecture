"""Skills reference only real skills and commands, and check the tools against their own plugin."""

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "plugin" / "skills").is_dir())
SKILLS_DIR = REPO_ROOT / "plugin" / "skills"
SKILL_FILES = sorted(SKILLS_DIR.glob("*/SKILL.md"))
MANIFEST = REPO_ROOT / "shared" / "cli.yaml"

COMMAND_RE = re.compile(r"(?<![\w/.-])((?:la|dr)-[a-z][a-z-]*[a-z])\b")
SKILL_REF_RE = re.compile(r"\bla:([a-z][a-z-]*[a-z])\b")
PREFLIGHT = "`la-doctor --plugin <this skill's base directory>`"


def _id(path: Path) -> str:
    return path.parent.name


def test_skills_exist():
    assert len(SKILL_FILES) >= 17


@pytest.mark.parametrize("path", SKILL_FILES, ids=_id)
def test_frontmatter_name_matches_directory(path):
    m = re.match(r"---\nname: (\S+)\ndescription: .+?\n---\n", path.read_text(encoding="utf-8"), re.DOTALL)
    assert m, "missing name/description frontmatter"
    assert m.group(1) == path.parent.name


@pytest.mark.parametrize("path", SKILL_FILES, ids=_id)
def test_skill_references_resolve(path):
    names = {p.parent.name for p in SKILL_FILES}
    refs = set(SKILL_REF_RE.findall(path.read_text(encoding="utf-8")))
    assert refs <= names, refs - names


def _manifest_commands() -> set[str]:
    return set(yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))["commands"])


@pytest.mark.parametrize("path", SKILL_FILES, ids=_id)
def test_commands_exist_in_the_manifest(path):
    used = set(COMMAND_RE.findall(path.read_text(encoding="utf-8")))
    assert used <= _manifest_commands(), used - _manifest_commands()


@pytest.mark.parametrize("path", SKILL_FILES, ids=_id)
def test_tool_users_run_the_plugin_preflight(path):
    text = path.read_text(encoding="utf-8")
    if set(COMMAND_RE.findall(text)) - {"la-doctor"}:
        assert PREFLIGHT in text, "uses la-*/dr-* commands without the la-doctor preflight"


@pytest.mark.parametrize("path", SKILL_FILES, ids=_id)
def test_no_hardcoded_version_pin(path):
    assert "la-doctor --expect" not in path.read_text(encoding="utf-8")
