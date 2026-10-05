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
PREFLIGHT = "la-doctor --plugin <this skill's base directory>"
PREFLIGHT_CMD_RE = re.compile(rf"`{re.escape(PREFLIGHT)}(?: --require-config)?`")


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
        assert PREFLIGHT_CMD_RE.search(text), "uses la-*/dr-* commands without the la-doctor preflight"


@pytest.mark.parametrize("path", SKILL_FILES, ids=_id)
def test_no_hardcoded_version_pin(path):
    assert "la-doctor --expect" not in path.read_text(encoding="utf-8")


MAIN_SKILLS = {"init", "pr", "arch-init", "arch-cleanup", "deterministic-refactor"}
STAGES = {"pr-plan", "pr-tests", "pr-implement", "pr-review"}
REQUIRE_CONFIG = (MAIN_SKILLS - {"init"}) | STAGES
DOCS_DIR = REPO_ROOT / "docs"
DOCS_PAGES = [
    "living-architecture-explained.md",
    "skills.md",
    "configuration.md",
    "commands.md",
    "deterministic-refactoring.md",
    "development.md",
]
BLOB_PREFIX = "https://github.com/MotleyAI/living-architecture/blob/main/"
LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
TABLE_SKILL_RE = re.compile(r"^\|\s*`la:([a-z][a-z-]*[a-z])`\s*\|", re.MULTILINE)
PREFLIGHT_RE = re.compile(r"^\*\*Preflight:\*\*.*$", re.MULTILINE)


def _skill_text(name: str) -> str:
    return (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    m = re.search(rf"^{re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    assert m, f"missing section {heading!r}"
    return m.group(1)


def test_main_skill_set_exists():
    assert MAIN_SKILLS | STAGES <= {p.parent.name for p in SKILL_FILES}


@pytest.mark.parametrize("page", DOCS_PAGES)
def test_docs_page_exists(page):
    assert (DOCS_DIR / page).is_file()


def test_docs_skills_lists_every_skill_once_in_its_role():
    text = (DOCS_DIR / "skills.md").read_text(encoding="utf-8")
    listed = TABLE_SKILL_RE.findall(text)
    assert sorted(listed) == sorted(p.parent.name for p in SKILL_FILES)
    assert set(TABLE_SKILL_RE.findall(_section(text, "## Main skills"))) == MAIN_SKILLS
    helpers = {p.parent.name for p in SKILL_FILES} - MAIN_SKILLS
    assert set(TABLE_SKILL_RE.findall(_section(text, "## Helper skills"))) == helpers


def test_readme_skills_table_lists_exactly_the_main_skills():
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    listed = TABLE_SKILL_RE.findall(_section(text, "## Skills"))
    assert sorted(listed) == sorted(MAIN_SKILLS)


@pytest.mark.parametrize("path", SKILL_FILES, ids=_id)
def test_preflight_requires_config_only_in_main_skills_and_stages(path):
    text = path.read_text(encoding="utf-8")
    preflight = PREFLIGHT_RE.findall(text)
    if path.parent.name in REQUIRE_CONFIG:
        assert len(preflight) == 1
        assert f"`{PREFLIGHT} --require-config`" in preflight[0]
        assert "la:init" in text
        assert "fast path" in text
    else:
        assert all("--require-config" not in line for line in preflight)


def _doc_files() -> list[Path]:
    return [REPO_ROOT / "README.md", *sorted(DOCS_DIR.glob("*.md"))]


@pytest.mark.parametrize("doc", _doc_files(), ids=lambda p: p.name)
def test_doc_links_resolve(doc):
    for target in LINK_RE.findall(doc.read_text(encoding="utf-8")):
        path = target.split("#", 1)[0]
        if target.startswith(BLOB_PREFIX):
            assert (REPO_ROOT / path.removeprefix(BLOB_PREFIX)).exists(), target
        elif path and not re.match(r"[a-z]+:", path):
            assert (doc.parent / path).exists(), target


def test_readme_links_into_docs_are_absolute():
    targets = LINK_RE.findall((REPO_ROOT / "README.md").read_text(encoding="utf-8"))
    docs_links = [t for t in targets if re.search(r"(^|/)docs/[^#]*\.md(#|$)", t)]
    for link in docs_links:
        assert link.startswith(BLOB_PREFIX + "docs/"), link
        assert (REPO_ROOT / link.split("#", 1)[0].removeprefix(BLOB_PREFIX)).is_file(), link
    assert docs_links


@pytest.mark.parametrize("name", ["init", "arch-init", "arch-cleanup"])
def test_new_skill_exists(name):
    assert (SKILLS_DIR / name / "SKILL.md").is_file()


def test_arch_slice_is_gone():
    assert not (SKILLS_DIR / "arch-slice").exists()
    files = [
        *REPO_ROOT.joinpath("plugin").rglob("*"),
        *DOCS_DIR.rglob("*"),
        REPO_ROOT / "README.md",
        REPO_ROOT / "AGENTS.md",
    ]
    hits = [
        f for f in files if f.is_file() and "arch-slice" in f.read_text(encoding="utf-8", errors="replace")
    ]
    assert not hits


def test_living_architecture_is_a_reference():
    text = _skill_text("living-architecture")
    assert not re.search(r"^## (Init|Migrate)\b", text, re.MULTILINE)
    assert "la:arch-init" in text


@pytest.mark.parametrize("path", SKILL_FILES, ids=_id)
def test_no_removed_review_settings(path):
    text = path.read_text(encoding="utf-8")
    for removed in ("reviewers.coderabbit", "reviewers.sonar.enabled", "--skip-coderabbit"):
        assert removed not in text


def test_process_reviews_detects_bots_per_pr():
    assert "la-pr-reviewers" in _skill_text("process-reviews")


@pytest.mark.parametrize("path", SKILL_FILES, ids=_id)
def test_codex_steps_follow_the_config(path):
    text = path.read_text(encoding="utf-8")
    if "mcp__codex__codex" in text or path.parent.name == "codex-review":
        assert "reviewers.codex" in text


@pytest.mark.parametrize("name", ["pr-implement", "pr-review", "arch-cleanup", "deterministic-refactor"])
def test_typecheck_gate(name):
    assert "la-typecheck" in _skill_text(name)


def test_pr_follows_tracker_and_openspec_config():
    text = _skill_text("pr")
    assert "la-config get tracker" in text
    assert "la-config get openspec" in text
    assert "gh issue develop --list" in text
