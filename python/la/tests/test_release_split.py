"""scripts/release-check over the two packages: lockstep versions and pins, per-package hashes, tool inputs, formats."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from deterministic_refactor.contract import compute_hash

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir())
DR_CONFIG = "shared/dr/config.yaml"
OLD_CONFIG = "shared/config.yaml"
SNAPSHOTS = {
    "python/dr/src/deterministic_refactor/contract/data/CONTRACT_HASH": "dr",
    "python/la/src/living_architecture/contract/data/CONTRACT_HASH": "la",
    "node/dr/src/contract/data/CONTRACT_HASH": "dr",
    "node/la/src/contract/data/CONTRACT_HASH": "la",
}
FILES = {
    "shared/dr/cli.yaml": "commands: {dr-x: {}}\n",
    DR_CONFIG: (
        "files: [deterministic-refactor.yaml, living-architecture.yaml]\nformats:\n"
        "  deterministic-refactor.yaml: [0.12.0]\n  living-architecture.yaml: [0.4.0, 0.12.0]\n"
    ),
    "shared/la/cli.yaml": "commands: {la-x: {}}\n",
    "conformance/dr/README.md": "# dr corpus\n",
    "conformance/la/README.md": "# la corpus\n",
    "python/dr/src/deterministic_refactor/__init__.py": "",
    "python/la/src/living_architecture/__init__.py": "",
    "python/la/tests/test_x.py": "",
    "node/scripts/conformance.mjs": "",
    "node/dr/src/index.ts": "export {};\n",
    "node/la/src/index.ts": "export {};\n",
    "node/dr/scripts/build.mjs": "",
    "node/la/scripts/build.mjs": "",
    "node/dr/tsconfig.json": "{}\n",
    "node/la/tsconfig.json": "{}\n",
    "node/la/tsconfig.build.json": "{}\n",
    "plugin/la/skills/pr/SKILL.md": "skill\n",
    "docs/index.md": "docs\n",
}
TOOLS = [
    "shared/dr/cli.yaml", "shared/la/cli.yaml", "shared/la/new.yaml", "conformance/dr/README.md",
    "conformance/la/README.md", "python/dr/src/deterministic_refactor/__init__.py",
    "python/la/src/living_architecture/__init__.py", "node/scripts/conformance.mjs", "node/dr/src/index.ts",
    "node/la/src/index.ts", "node/dr/scripts/build.mjs", "node/la/scripts/build.mjs", "node/dr/tsconfig.json",
    "node/la/tsconfig.build.json",
]
DEPENDENCY_MANIFESTS = [
    "python/dr/pyproject.toml", "python/la/pyproject.toml", "python/uv.lock", "node/dr/package.json",
    "node/la/package.json", "node/package-lock.json",
]


def _minor(version: str) -> str:
    return ".".join(version.split(".")[:2])


def _next_minor(version: str) -> str:
    major, minor = version.split(".")[:2]
    return f"{major}.{int(minor) + 1}"


class SplitReleaseRepo:
    """A git repo in the two-package layout with this checkout's scripts/."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.dep = "6.0.2"
        self.overrides: dict[str, str] = {}
        shutil.copytree(REPO_ROOT / "scripts", root / "scripts")
        for rel, text in FILES.items():
            self.write(rel, text)
        home = root.parent / f"{root.name}-home"
        home.mkdir()
        (home / ".gitconfig").write_text("", encoding="utf-8")
        self.env = {
            **os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"),
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
        }
        self.git("init", "-q", "-b", "main")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.root, env=self.env, capture_output=True, text=True, check=True).stdout

    def write(self, rel: str, text: str) -> None:
        (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.root / rel).write_text(text, encoding="utf-8")

    def change(self, rel: str) -> None:
        path = self.root / rel
        self.write(rel, (path.read_text(encoding="utf-8") if path.exists() else "") + "changed\n")

    def manifests(self, version: str) -> dict[str, str]:
        """Every manifest and lockfile at `version`, la pinning dr to its minor."""
        base = f"{_minor(version)}.0"
        pin, tilde = f">={base},<{_next_minor(version)}", f"~{base}"
        return {
            "python/pyproject.toml": '[tool.uv.workspace]\nmembers = ["dr", "la", "conformance"]\n',
            "python/dr/pyproject.toml": (
                f'[project]\nname = "deterministic-refactor"\nversion = "{version}"\n'
                f'dependencies = ["pyyaml>={self.dep}"]\n'
            ),
            "python/la/pyproject.toml": (
                f'[project]\nname = "living-architecture"\nversion = "{version}"\n'
                f'dependencies = ["deterministic-refactor{pin}", "pyyaml>={self.dep}"]\n'
            ),
            "python/uv.lock": (
                f'version = 1\n\n[[package]]\nname = "deterministic-refactor"\nversion = "{version}"\n'
                f'source = {{ editable = "dr" }}\n\n[[package]]\nname = "living-architecture"\nversion = "{version}"\n'
                f'source = {{ editable = "la" }}\n\n[[package]]\nname = "pyyaml"\nversion = "{self.dep}"\n'
            ),
            "node/package.json": '{"name": "workspace", "private": true, "workspaces": ["dr", "la"]}\n',
            "node/dr/package.json": (
                f'{{"name": "deterministic-refactor", "version": "{version}", "dependencies": {{"ajv": "^{self.dep}"}}}}\n'
            ),
            "node/la/package.json": (
                f'{{"name": "living-architecture", "version": "{version}",'
                f' "dependencies": {{"deterministic-refactor": "{tilde}", "ajv": "^{self.dep}"}}}}\n'
            ),
            "node/package-lock.json": (
                f'{{"name": "workspace", "lockfileVersion": 3, "packages": {{'
                f'"": {{"name": "workspace", "workspaces": ["dr", "la"]}}, '
                f'"dr": {{"name": "deterministic-refactor", "version": "{version}"}}, '
                f'"la": {{"name": "living-architecture", "version": "{version}",'
                f' "dependencies": {{"deterministic-refactor": "{tilde}"}}}}, '
                f'"node_modules/ajv": {{"version": "{self.dep}"}}}}}}\n'
            ),
            "plugin/dr/.claude-plugin/plugin.json": f'{{"name": "dr", "version": "{version}"}}\n',
            "plugin/la/.claude-plugin/plugin.json": (
                f'{{"name": "la", "version": "{version}", "dependencies": [{{"name": "dr", "version": "{tilde}"}}]}}\n'
            ),
        }

    def sync_hashes(self) -> None:
        for rel, package in SNAPSHOTS.items():
            self.write(rel, compute_hash(self.root / "shared" / package) + "\n")

    def release(self, version: str) -> None:
        for rel, text in {**self.manifests(version), **self.overrides}.items():
            self.write(rel, text)
        self.sync_hashes()
        for rel, text in self.overrides.items():
            self.write(rel, text)
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", f"release {version}")
        self.git("tag", f"v{version}")

    def release_check(self, tag: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(self.root / "scripts" / "release-check"), tag], cwd=self.root,
                              env=self.env, capture_output=True, text=True, check=False)


@pytest.fixture
def split_repo(tmp_path: Path) -> SplitReleaseRepo:
    return SplitReleaseRepo(tmp_path / "repo")


def _accepted(proc: subprocess.CompletedProcess[str]) -> None:
    assert proc.returncode == 0, proc.stderr


def _refused(proc: subprocess.CompletedProcess[str], *needles: str) -> None:
    assert proc.returncode == 1, proc.stderr
    for needle in needles:
        assert needle in proc.stderr, (needle, proc.stderr)


def test_lockstep_release_is_accepted(split_repo: SplitReleaseRepo) -> None:
    split_repo.release("0.12.0")
    split_repo.release("0.12.1")
    _accepted(split_repo.release_check("v0.12.1"))


@pytest.mark.parametrize("rel", TOOLS)
def test_each_tool_input_of_either_package_counts(split_repo: SplitReleaseRepo, rel: str) -> None:
    split_repo.release("0.12.0")
    split_repo.change(rel)
    split_repo.release("0.12.1")
    _refused(split_repo.release_check("v0.12.1"), "v0.12.0", rel)


def test_a_tool_change_released_as_a_minor_passes(split_repo: SplitReleaseRepo) -> None:
    split_repo.release("0.12.0")
    split_repo.change("python/dr/src/deterministic_refactor/__init__.py")
    split_repo.release("0.13.0")
    _accepted(split_repo.release_check("v0.13.0"))


def test_plugin_docs_and_tests_only_patch_is_accepted(split_repo: SplitReleaseRepo) -> None:
    split_repo.release("0.12.0")
    for rel in ("plugin/la/skills/pr/SKILL.md", "docs/index.md", "python/la/tests/test_x.py"):
        split_repo.change(rel)
    split_repo.release("0.12.1")
    _accepted(split_repo.release_check("v0.12.1"))


@pytest.mark.parametrize("manifest", DEPENDENCY_MANIFESTS)
def test_a_dependency_change_counts(split_repo: SplitReleaseRepo, manifest: str) -> None:
    split_repo.release("0.12.0")
    split_repo.dep = "9.9.9"
    split_repo.release("0.12.1")
    _refused(split_repo.release_check("v0.12.1"), "v0.12.0", manifest)


def test_the_pins_moving_with_a_minor_bump_do_not_count_as_a_change(split_repo: SplitReleaseRepo) -> None:
    split_repo.release("0.12.0")
    split_repo.change("docs/index.md")
    split_repo.release("0.13.0")
    _accepted(split_repo.release_check("v0.13.0"))


@pytest.mark.parametrize(
    "rel",
    [
        "python/dr/pyproject.toml", "python/la/pyproject.toml", "node/dr/package.json", "node/la/package.json",
        "plugin/dr/.claude-plugin/plugin.json", "plugin/la/.claude-plugin/plugin.json",
    ],
)
def test_a_version_out_of_lockstep_is_refused(split_repo: SplitReleaseRepo, rel: str) -> None:
    split_repo.release("0.12.0")
    split_repo.overrides[rel] = split_repo.manifests("0.13.0")[rel]
    split_repo.release("0.12.1")
    _refused(split_repo.release_check("v0.12.1"), rel)


@pytest.mark.parametrize(
    ("rel", "old", "new"),
    [
        ("python/la/pyproject.toml", "deterministic-refactor>=0.12.0,<0.13", "deterministic-refactor>=0.11.0,<0.12"),
        ("node/la/package.json", '"deterministic-refactor": "~0.12.0"', '"deterministic-refactor": "~0.11.0"'),
        ("plugin/la/.claude-plugin/plugin.json", '"version": "~0.12.0"', '"version": "~0.11.0"'),
    ],
    ids=["pypi-pin", "npm-pin", "plugin-dependency"],
)
def test_la_pinning_another_dr_minor_is_refused(split_repo: SplitReleaseRepo, rel: str, old: str, new: str) -> None:
    split_repo.release("0.12.0")
    text = split_repo.manifests("0.12.1")[rel]
    assert old in text
    split_repo.overrides[rel] = text.replace(old, new)
    split_repo.release("0.12.1")
    _refused(split_repo.release_check("v0.12.1"), rel)


def test_package_hashes_may_differ(split_repo: SplitReleaseRepo) -> None:
    split_repo.release("0.12.0")
    split_repo.release("0.12.1")
    hashes = {(split_repo.root / rel).read_text(encoding="utf-8") for rel in SNAPSHOTS}
    assert len(hashes) == 2
    _accepted(split_repo.release_check("v0.12.1"))


@pytest.mark.parametrize("rel", SNAPSHOTS)
def test_a_stale_snapshot_hash_is_refused_by_name(split_repo: SplitReleaseRepo, rel: str) -> None:
    split_repo.release("0.12.0")
    split_repo.overrides[rel] = "stale\n"
    split_repo.release("0.12.1")
    _refused(split_repo.release_check("v0.12.1"), rel)


def _old_layout_release(split_repo: SplitReleaseRepo, formats: str) -> None:
    """v0.11.0 in the single-package layout with `shared/config.yaml`."""
    saved = {rel: (split_repo.root / rel).read_text(encoding="utf-8") for rel in FILES}
    shutil.rmtree(split_repo.root / "shared")
    split_repo.write(OLD_CONFIG, f"file: living-architecture.yaml\n{formats}\n")
    split_repo.write("python/pyproject.toml", '[project]\nname = "living-architecture"\nversion = "0.11.0"\n')
    split_repo.write("plugin/.claude-plugin/plugin.json", '{"name": "la", "version": "0.11.0"}\n')
    split_repo.git("add", "-A")
    split_repo.git("commit", "-q", "-m", "release 0.11.0")
    split_repo.git("tag", "v0.11.0")
    split_repo.git("rm", "-q", "-r", "shared", "plugin/.claude-plugin")
    for rel, text in saved.items():
        split_repo.write(rel, text)


@pytest.mark.parametrize("previous", ["formats: [0.4.0]", "format: 0.4.0"])
def test_split_release_reads_the_single_file_layout(split_repo: SplitReleaseRepo, previous: str) -> None:
    _old_layout_release(split_repo, previous)
    split_repo.release("0.12.0")
    _accepted(split_repo.release_check("v0.12.0"))


def test_split_release_appending_another_version_is_refused(split_repo: SplitReleaseRepo) -> None:
    _old_layout_release(split_repo, "formats: [0.4.0]")
    split_repo.write(DR_CONFIG, FILES[DR_CONFIG].replace("[0.4.0, 0.12.0]", "[0.4.0, 0.13.0]"))
    split_repo.release("0.12.0")
    _refused(split_repo.release_check("v0.12.0"), "living-architecture.yaml", "[0.4.0]", "[0.4.0, 0.13.0]", "0.12.0")


def test_per_file_formats_compared_between_split_releases(split_repo: SplitReleaseRepo) -> None:
    split_repo.release("0.12.0")
    split_repo.write(DR_CONFIG, FILES[DR_CONFIG].replace("deterministic-refactor.yaml: [0.12.0]",
                                                         "deterministic-refactor.yaml: [0.12.0, 0.13.0]"))
    split_repo.release("0.13.0")
    _accepted(split_repo.release_check("v0.13.0"))


def test_a_file_dropping_a_format_between_split_releases_is_refused(split_repo: SplitReleaseRepo) -> None:
    split_repo.release("0.12.0")
    split_repo.write(DR_CONFIG, FILES[DR_CONFIG].replace("[0.4.0, 0.12.0]", "[0.12.0]"))
    split_repo.release("0.13.0")
    _refused(split_repo.release_check("v0.13.0"), "living-architecture.yaml", "[0.4.0, 0.12.0]", "[0.12.0]")


@pytest.fixture(scope="module")
def release_rule() -> ModuleType:
    spec = importlib.util.spec_from_file_location("release_rule", REPO_ROOT / "scripts" / "release_rule.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_per_file_formats_reader_reads_like_yaml(release_rule: ModuleType) -> None:
    text = (REPO_ROOT / DR_CONFIG).read_text(encoding="utf-8")
    assert release_rule.parse_file_formats(text) == yaml.safe_load(text)["formats"]
