"""Skill shapes across both plugins, the docs listing them, and the docs' links."""

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir())
PLUGIN_DIR = REPO_ROOT / "plugin"
SKILL_FILES = sorted(PLUGIN_DIR.glob("*/skills/*/SKILL.md"))
LEAKS = yaml.safe_load((REPO_ROOT / "shared" / "dr" / "vectors" / "skill-leaks.yaml").read_text(encoding="utf-8"))
PREFLIGHT = "{doctor} --plugin <this skill's base directory>"


def _qualified(path: Path) -> str:
    """`<plugin>:<skill>` of a SKILL.md path."""
    return f"{path.parents[2].name}:{path.parent.name}"


def _id(path: Path) -> str:
    return _qualified(path)


def _doctor(path: Path) -> str:
    return f"{path.parents[2].name}-doctor"


def test_skills_exist():
    assert len(SKILL_FILES) >= 18


@pytest.mark.parametrize("path", SKILL_FILES, ids=_id)
def test_frontmatter_name_matches_directory(path):
    m = re.match(r"---\nname: (\S+)\ndescription: .+?\n---\n", path.read_text(encoding="utf-8"), re.DOTALL)
    assert m, "missing name/description frontmatter"
    assert m.group(1) == path.parent.name


MAIN_SKILLS = {"la:init", "la:pr", "la:arch-init", "la:arch-cleanup", "dr:init", "dr:deterministic-refactor"}
# The README's table: la:init names la:arch-init in its purpose; docs/skills.md lists every main skill.
README_SKILLS = {"la:init", "la:pr", "dr:init", "dr:deterministic-refactor"}
STAGES = {"la:pr-plan", "la:pr-tests", "la:pr-implement", "la:pr-review"}
REQUIRE_CONFIG = MAIN_SKILLS - {"la:init", "dr:init"}
REQUIRE_PLAN_STORE = {"la:pr"}
DOCS_DIR = REPO_ROOT / "docs"
DOCS_PAGES = [
    "how-it-works.md",
    "living-architecture-in-questions-and-answers.md",
    "skills.md",
    "configuration.md",
    "commands.md",
    "deterministic-refactoring.md",
    "development.md",
]
BLOB_PREFIX = "https://github.com/MotleyAI/living-architecture/blob/main/"
RAW_PREFIX = "https://raw.githubusercontent.com/MotleyAI/living-architecture/main/"
LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
TABLE_SKILL_RE = re.compile(r"^\|\s*`((?:la|dr):[a-z][a-z-]*[a-z])`\s*\|", re.MULTILINE)
PREFLIGHT_RE = re.compile(r"^\*\*Preflight:\*\*.*$", re.MULTILINE)


def _skill_text(qualified: str) -> str:
    plugin, name = qualified.split(":")
    return (PLUGIN_DIR / plugin / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    m = re.search(rf"^{re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    assert m, f"missing section {heading!r}"
    return m.group(1)


def test_main_skill_set_exists():
    assert MAIN_SKILLS | STAGES <= {_qualified(p) for p in SKILL_FILES}


@pytest.mark.parametrize("page", DOCS_PAGES)
def test_docs_page_exists(page):
    assert (DOCS_DIR / page).is_file()


def test_docs_skills_lists_every_skill_once_in_its_role():
    text = (DOCS_DIR / "skills.md").read_text(encoding="utf-8")
    listed = TABLE_SKILL_RE.findall(text)
    assert sorted(listed) == sorted(_qualified(p) for p in SKILL_FILES)
    assert set(TABLE_SKILL_RE.findall(_section(text, "## Main skills"))) == MAIN_SKILLS
    helpers = {_qualified(p) for p in SKILL_FILES} - MAIN_SKILLS
    assert set(TABLE_SKILL_RE.findall(_section(text, "## Helper skills"))) == helpers


def test_readme_skills_table_lists_exactly_the_entry_skills():
    text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    listed = TABLE_SKILL_RE.findall(_section(text, "## Skills"))
    assert sorted(listed) == sorted(README_SKILLS)


@pytest.mark.parametrize("path", SKILL_FILES, ids=_id)
def test_preflight_requires_config_only_in_main_skills(path):
    preflight = PREFLIGHT_RE.findall(path.read_text(encoding="utf-8"))
    skill = _qualified(path)
    if skill in REQUIRE_CONFIG:
        assert len(preflight) == 1
        flags = " --require-plan-store" if skill in REQUIRE_PLAN_STORE else ""
        assert f"`{PREFLIGHT.format(doctor=_doctor(path))} --require-config{flags}`" in preflight[0]
    elif skill in STAGES:
        assert preflight == []
    else:
        assert all("--require-config" not in line for line in preflight)


def _doc_files() -> list[Path]:
    community = [REPO_ROOT / name for name in ("README.md", "CONTRIBUTING.md", "SECURITY.md")]
    return [*community, *sorted(DOCS_DIR.glob("*.md"))]


def _anchors(doc: Path) -> set[str]:
    """GitHub's heading anchors in `doc`, fenced code skipped."""
    prose = re.sub(r"^```.*?^```$", "", doc.read_text(encoding="utf-8"), flags=re.MULTILINE | re.DOTALL)
    headings = re.findall(r"^#+ (.+)$", prose, re.MULTILINE)
    return {re.sub(r"[^\w\- ]", "", h.lower()).replace(" ", "-") for h in headings}


@pytest.mark.parametrize("doc", _doc_files(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix())
def test_doc_links_into_the_repo_resolve(doc):
    """Relative and GitHub blob/raw links name an existing repo file and heading; other URLs are not fetched."""
    for target in LINK_RE.findall(doc.read_text(encoding="utf-8")):
        path, _, anchor = target.partition("#")
        if target.startswith((BLOB_PREFIX, RAW_PREFIX)):
            resolved = REPO_ROOT / path.removeprefix(BLOB_PREFIX).removeprefix(RAW_PREFIX)
        elif re.match(r"[a-z]+:", path):
            continue
        else:
            resolved = doc.parent / path if path else doc
        assert resolved.exists(), target
        if anchor and resolved.suffix == ".md":
            assert anchor in _anchors(resolved), target


def test_readme_image_is_absolute_and_in_the_repo():
    # A bare image, not a badge (an image wrapped in a link).
    images = re.findall(r"(?<!\[)!\[[^\]]+\]\(([^)\s]+)\)", (REPO_ROOT / "README.md").read_text(encoding="utf-8"))
    assert images
    for image in images:
        assert image.startswith(RAW_PREFIX), image
        assert (REPO_ROOT / image.removeprefix(RAW_PREFIX)).is_file(), image


def test_readme_links_into_docs_are_absolute():
    targets = LINK_RE.findall((REPO_ROOT / "README.md").read_text(encoding="utf-8"))
    docs_links = [t for t in targets if re.search(r"(^|/)docs/[^#]*\.md(#|$)", t)]
    for link in docs_links:
        assert link.startswith(BLOB_PREFIX + "docs/"), link
        assert (REPO_ROOT / link.split("#", 1)[0].removeprefix(BLOB_PREFIX)).is_file(), link
    assert docs_links


@pytest.mark.parametrize("name", ["init", "arch-init", "arch-cleanup"])
def test_new_skill_exists(name):
    assert (PLUGIN_DIR / "la" / "skills" / name / "SKILL.md").is_file()


def test_arch_slice_is_gone():
    assert not list(PLUGIN_DIR.glob("*/skills/arch-slice"))
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
    assert not re.search(r"^## (Init|Migrate)\b", _skill_text("la:living-architecture"), re.MULTILINE)


@pytest.mark.parametrize("path", SKILL_FILES, ids=_id)
def test_no_removed_review_settings(path):
    text = path.read_text(encoding="utf-8")
    for removed in ("reviewers.coderabbit", "reviewers.sonar.enabled", "--skip-coderabbit"):
        assert removed not in text


def test_process_reviews_detects_bots_per_pr():
    assert "la-pr-reviewers" in _skill_text("la:process-reviews")


@pytest.mark.parametrize("path", SKILL_FILES, ids=_id)
def test_codex_steps_follow_the_config(path):
    text = path.read_text(encoding="utf-8")
    if "mcp__codex__codex" in text or path.parent.name == "codex-review":
        assert "reviewers.codex" in text


@pytest.mark.parametrize("name", ["la:pr-implement", "la:pr-review", "la:arch-cleanup", "dr:deterministic-refactor"])
def test_typecheck_gate(name):
    assert "dr-typecheck" in _skill_text(name)


def test_pr_follows_tracker_and_openspec_config():
    text = _skill_text("la:pr")
    assert "la-config get tracker" in text
    assert "la-config get openspec" in text
    assert "gh issue develop --list" in text


def _leaks(text: str) -> list[str]:
    tokens = sorted({token for tokens in LEAKS.values() for token in tokens})
    return [token for token in tokens if re.search(rf"(?<!\w){re.escape(token)}(?!\w)", text)]


def test_leak_matcher_needs_whole_tokens():
    assert _leaks("run basedpyright, then `*.py` files") == ["*.py", "basedpyright"]
    assert _leaks("europe tscx jester") == []


@pytest.mark.parametrize("path", SKILL_FILES, ids=_id)
def test_no_language_only_token(path):
    assert _leaks(path.read_text(encoding="utf-8")) == [], f"{path.parent.name} names language-only tokens"


RETIRED_ARC42_FORMS = ["architecture/**/*.arc42.md", "arc42 '", "<node>.arc42.md", "touches unknown node"]


@pytest.mark.parametrize("path", SKILL_FILES, ids=_id)
def test_skills_name_only_flat_id_named_arc42_docs(path):
    text = path.read_text(encoding="utf-8")
    assert [form for form in RETIRED_ARC42_FORMS if form in text] == []


@pytest.mark.parametrize("name", ["dr:deterministic-refactor", "la:arch-cleanup", "dr:make-diff-compliant"])
def test_soundness_skills_keep_the_full_suite(name):
    assert "local test scope" not in _skill_text(name)


def test_commands_doc_lists_affected_tests():
    rows = [line for line in (DOCS_DIR / "commands.md").read_text(encoding="utf-8").splitlines()
            if line.startswith("| `la-affected-tests")]
    assert len(rows) == 1
