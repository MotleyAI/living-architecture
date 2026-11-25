"""scripts/release-check over the two packages: lockstep versions and pins, per-package hashes, tool inputs, formats."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest
import yaml

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir())
TRMV_CONFIG = "shared/trmv/config.yaml"
OLD_CONFIG = "shared/config.yaml"
SPLIT_CONFIG = (
    "files: [trmv.yaml, living-architecture.yaml]\nformats:\n"
    "  trmv.yaml: [0.12.0]\n  living-architecture.yaml: [0.4.0, 0.12.0]\n"
)
SNAPSHOTS = [
    "python/trmv/src/trmv/contract/data/CONTRACT_HASH",
    "python/la/src/living_architecture/contract/data/CONTRACT_HASH",
    "node/trmv/src/contract/data/CONTRACT_HASH",
    "node/la/src/contract/data/CONTRACT_HASH",
]
TOOLS = [
    "shared/trmv/cli.yaml", "shared/la/cli.yaml", "shared/la/new.yaml", "conformance/trmv/README.md",
    "conformance/la/README.md", "python/trmv/src/trmv/__init__.py",
    "python/la/src/living_architecture/__init__.py", "node/scripts/conformance.mjs", "node/trmv/src/index.ts",
    "node/la/src/index.ts", "node/trmv/scripts/build.mjs", "node/la/scripts/build.mjs", "node/trmv/tsconfig.json",
    "node/la/tsconfig.build.json",
]
DEPENDENCY_MANIFESTS = [
    "python/trmv/pyproject.toml", "python/la/pyproject.toml", "python/uv.lock", "node/trmv/package.json",
    "node/la/package.json", "node/package-lock.json",
]


@pytest.fixture
def split_repo(release_repo):
    """The release repo with formats for 0.12.0 releases."""
    release_repo.write(TRMV_CONFIG, SPLIT_CONFIG)
    return release_repo


def _accepted(proc: subprocess.CompletedProcess[str]) -> None:
    assert proc.returncode == 0, proc.stderr


def _refused(proc: subprocess.CompletedProcess[str], *needles: str) -> None:
    assert proc.returncode == 1, proc.stderr
    for needle in needles:
        assert needle in proc.stderr, (needle, proc.stderr)


def test_lockstep_release_is_accepted(split_repo) -> None:
    split_repo.release("0.12.0")
    split_repo.release("0.12.1")
    _accepted(split_repo.release_check("v0.12.1"))


@pytest.mark.parametrize("rel", TOOLS)
def test_each_tool_input_of_either_package_counts(split_repo, rel: str) -> None:
    split_repo.release("0.12.0")
    split_repo.change(rel)
    split_repo.release("0.12.1")
    _refused(split_repo.release_check("v0.12.1"), "v0.12.0", rel)


def test_a_tool_change_released_as_a_minor_passes(split_repo) -> None:
    split_repo.release("0.12.0")
    split_repo.change("python/trmv/src/trmv/__init__.py")
    split_repo.release("0.13.0")
    _accepted(split_repo.release_check("v0.13.0"))


def test_plugin_docs_and_tests_only_patch_is_accepted(split_repo) -> None:
    split_repo.release("0.12.0")
    for rel in ("plugin/la/skills/pr/SKILL.md", "docs/index.md", "python/la/tests/test_x.py"):
        split_repo.change(rel)
    split_repo.release("0.12.1")
    _accepted(split_repo.release_check("v0.12.1"))


@pytest.mark.parametrize("manifest", DEPENDENCY_MANIFESTS)
def test_a_dependency_change_counts(split_repo, manifest: str) -> None:
    split_repo.release("0.12.0")
    split_repo.deps = {rel: ("==9.9.9" if rel.endswith("pyproject.toml") else "9.9.9") for rel in split_repo.deps}
    split_repo.release("0.12.1")
    _refused(split_repo.release_check("v0.12.1"), "v0.12.0", manifest)


def test_the_pins_moving_with_a_minor_bump_do_not_count_as_a_change(split_repo) -> None:
    split_repo.release("0.12.0")
    split_repo.change("docs/index.md")
    split_repo.release("0.13.0")
    _accepted(split_repo.release_check("v0.13.0"))


@pytest.mark.parametrize(
    "rel",
    [
        "python/trmv/pyproject.toml", "python/la/pyproject.toml", "node/trmv/package.json", "node/la/package.json",
        "plugin/trmv/.claude-plugin/plugin.json", "plugin/la/.claude-plugin/plugin.json",
    ],
)
def test_a_version_out_of_lockstep_is_refused(split_repo, rel: str) -> None:
    split_repo.release("0.12.0")
    split_repo.overrides[rel] = split_repo.manifests("0.13.0")[rel]
    split_repo.release("0.12.1")
    _refused(split_repo.release_check("v0.12.1"), rel)


@pytest.mark.parametrize(
    ("rel", "old", "new"),
    [
        ("python/la/pyproject.toml", "type-rename-move>=0.12.0,<0.13", "type-rename-move>=0.11.0,<0.12"),
        ("node/la/package.json", '"type-rename-move": "~0.12.0"', '"type-rename-move": "~0.11.0"'),
        ("plugin/la/.claude-plugin/plugin.json", '"version": "~0.12.0"', '"version": "~0.11.0"'),
    ],
    ids=["pypi-pin", "npm-pin", "plugin-dependency"],
)
def test_la_pinning_another_trmv_minor_is_refused(split_repo, rel: str, old: str, new: str) -> None:
    split_repo.release("0.12.0")
    text = split_repo.manifests("0.12.1")[rel]
    assert old in text
    split_repo.overrides[rel] = text.replace(old, new)
    split_repo.release("0.12.1")
    _refused(split_repo.release_check("v0.12.1"), rel)


def test_package_hashes_may_differ(split_repo) -> None:
    split_repo.release("0.12.0")
    split_repo.release("0.12.1")
    hashes = {(split_repo.root / rel).read_text(encoding="utf-8") for rel in SNAPSHOTS}
    assert len(hashes) == 2
    _accepted(split_repo.release_check("v0.12.1"))


@pytest.mark.parametrize("rel", SNAPSHOTS)
def test_a_stale_snapshot_hash_is_refused_by_name(split_repo, rel: str) -> None:
    split_repo.release("0.12.0")
    split_repo.overrides[rel] = "stale\n"
    split_repo.release("0.12.1")
    _refused(split_repo.release_check("v0.12.1"), rel)


def _old_layout_release(split_repo, formats: str, version: str = "0.11.0") -> None:
    """`version` in the single-package layout with `shared/config.yaml`."""
    shared = split_repo.root / "shared"
    saved = {p.relative_to(split_repo.root).as_posix(): p.read_text(encoding="utf-8") for p in shared.rglob("*") if p.is_file()}
    shutil.rmtree(split_repo.root / "shared")
    split_repo.write(OLD_CONFIG, f"file: living-architecture.yaml\n{formats}\n")
    split_repo.write("python/pyproject.toml", f'[project]\nname = "living-architecture"\nversion = "{version}"\n')
    split_repo.write("plugin/.claude-plugin/plugin.json", f'{{"name": "la", "version": "{version}"}}\n')
    split_repo.git("add", "-A")
    split_repo.git("commit", "-q", "-m", f"release {version}")
    split_repo.git("tag", f"v{version}")
    split_repo.git("rm", "-q", "-r", "shared", "plugin/.claude-plugin")
    for rel, text in saved.items():
        split_repo.write(rel, text)


@pytest.mark.parametrize("previous", ["formats: [0.4.0]", "format: 0.4.0"])
def test_split_release_reads_the_single_file_layout(split_repo, previous: str) -> None:
    _old_layout_release(split_repo, previous)
    split_repo.release("0.12.0")
    _accepted(split_repo.release_check("v0.12.0"))


V0_13_0_FORMATS = (
    "local_file: living-architecture.local.yaml\n"
    "# Every released repo format (`format` in living-architecture.yaml), oldest first.\n"
    "formats: [0.4.0]"
)


def test_the_first_trmv_release_reads_v0_13_0_from_the_single_file_layout(split_repo) -> None:
    _old_layout_release(split_repo, V0_13_0_FORMATS, "0.13.0")
    split_repo.write(TRMV_CONFIG, (REPO_ROOT / TRMV_CONFIG).read_text(encoding="utf-8"))
    split_repo.release("0.14.0")
    _accepted(split_repo.release_check("v0.14.0"))


def test_split_release_appending_another_version_is_refused(split_repo) -> None:
    _old_layout_release(split_repo, "formats: [0.4.0]")
    split_repo.write(TRMV_CONFIG, SPLIT_CONFIG.replace("[0.4.0, 0.12.0]", "[0.4.0, 0.13.0]"))
    split_repo.release("0.12.0")
    _refused(split_repo.release_check("v0.12.0"), "living-architecture.yaml", "[0.4.0]", "[0.4.0, 0.13.0]", "0.12.0")


def test_per_file_formats_compared_between_split_releases(split_repo) -> None:
    split_repo.release("0.12.0")
    split_repo.write(TRMV_CONFIG, SPLIT_CONFIG.replace("trmv.yaml: [0.12.0]",
                                                         "trmv.yaml: [0.12.0, 0.13.0]"))
    split_repo.release("0.13.0")
    _accepted(split_repo.release_check("v0.13.0"))


def test_a_file_dropping_a_format_between_split_releases_is_refused(split_repo) -> None:
    split_repo.release("0.12.0")
    split_repo.write(TRMV_CONFIG, SPLIT_CONFIG.replace("[0.4.0, 0.12.0]", "[0.12.0]"))
    split_repo.release("0.13.0")
    _refused(split_repo.release_check("v0.13.0"), "living-architecture.yaml", "[0.4.0, 0.12.0]", "[0.12.0]")


def test_the_trmv_plugin_tag_at_the_release_commit_passes(split_repo) -> None:
    split_repo.release("0.12.0")
    split_repo.release("0.12.1")
    assert split_repo.git("rev-parse", "trmv--v0.12.1^{commit}") == split_repo.git("rev-parse", "v0.12.1^{commit}")
    _accepted(split_repo.release_check("v0.12.1"))


def test_a_missing_trmv_plugin_tag_is_refused(split_repo) -> None:
    split_repo.release("0.12.0")
    split_repo.release("0.12.1", plugin_tag=False)
    _refused(split_repo.release_check("v0.12.1"), "trmv--v0.12.1")


def test_a_trmv_plugin_tag_at_another_commit_is_refused(split_repo) -> None:
    split_repo.release("0.12.0")
    split_repo.git("tag", "trmv--v0.12.1")
    split_repo.release("0.12.1", plugin_tag=False)
    plugin, release = (split_repo.git("rev-parse", f"{tag}^{{commit}}").strip() for tag in ("trmv--v0.12.1", "v0.12.1"))
    assert plugin != release
    _refused(split_repo.release_check("v0.12.1"), "trmv--v0.12.1", plugin, release)


@pytest.fixture(scope="module")
def release_rule() -> ModuleType:
    spec = importlib.util.spec_from_file_location("release_rule", REPO_ROOT / "scripts" / "release_rule.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_per_file_formats_reader_reads_like_yaml(release_rule: ModuleType) -> None:
    text = (REPO_ROOT / TRMV_CONFIG).read_text(encoding="utf-8")
    assert release_rule.parse_file_formats(text) == yaml.safe_load(text)["formats"]
