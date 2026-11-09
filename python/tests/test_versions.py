import importlib.util
import json
import os
import re
import subprocess
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

from living_architecture import __version__, config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PROJECT_ROOT.parent
# An install pin: `living-architecture==X` (PyPI) or `living-architecture@X` (npm).
PIN = re.compile(r"living-architecture(?:==|@)(\d[\w.+-]*)")
# A tool input of the release rule.
TOOL = "python/src/living_architecture/__init__.py"


def _json(rel: str) -> dict:
    return json.loads((REPO_ROOT / rel).read_text(encoding="utf-8"))


def _plugin() -> dict:
    return _json("plugin/.claude-plugin/plugin.json")


def _marketplace() -> dict:
    return _json(".claude-plugin/marketplace.json")


def _npm_package() -> dict:
    return _json("node/package.json")


def _pyproject() -> dict:
    return tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def _plugin_version() -> str:
    return _plugin()["version"]


def test_plugin_and_package_versions_agree() -> None:
    assert _pyproject()["version"] == _plugin_version() == __version__


def test_marketplace_lists_the_plugin() -> None:
    [entry] = _marketplace()["plugins"]
    assert entry["name"] == _plugin()["name"]
    assert (REPO_ROOT / entry["source"] / ".claude-plugin" / "plugin.json").is_file()


@pytest.mark.parametrize("name", ["README.md", "LICENSE"])
def test_root_files_are_relative_symlinks(name: str) -> None:
    link = PROJECT_ROOT / name
    assert link.is_symlink(), f"python/{name} is not a symlink"
    assert os.readlink(link) == f"../{name}"
    assert link.resolve() == (REPO_ROOT / name).resolve()


def test_npm_package_version_agrees() -> None:
    assert (REPO_ROOT / "node" / "package.json").is_file(), "node/package.json is missing"
    assert _npm_package()["version"] == _plugin_version() == __version__


def test_package_listings_share_one_description() -> None:
    [entry] = _marketplace()["plugins"]
    descriptions = {_pyproject()["description"], _npm_package()["description"], _plugin()["description"]}
    assert descriptions == {entry["description"]}


def test_package_listings_share_the_keywords() -> None:
    keywords = _pyproject()["keywords"]
    assert keywords
    assert _npm_package()["keywords"] == _plugin()["keywords"] == keywords


def test_pypi_links_back_to_the_repo() -> None:
    urls = _pyproject()["urls"]
    assert urls["Repository"] == "https://github.com/MotleyAI/living-architecture"
    assert all(url.startswith(urls["Repository"]) for url in urls.values())


def test_python_classifiers_match_the_ci_matrix() -> None:
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    matrix = re.search(r"python-version: \[([^\]]*)\]", ci)
    assert matrix
    tested = [version.strip().strip('"') for version in matrix.group(1).split(",")]
    prefix = "Programming Language :: Python :: "
    declared = [c.removeprefix(prefix) for c in _pyproject()["classifiers"] if c.startswith(prefix + "3.")]
    assert declared == tested


def test_doc_pins_name_the_current_version() -> None:
    docs = [REPO_ROOT / "README.md", *sorted((REPO_ROOT / "docs").glob("*.md"))]
    pins = [(doc.name, version) for doc in docs for version in PIN.findall(doc.read_text(encoding="utf-8"))]
    assert pins, "no living-architecture version pin found in README.md or docs/"
    assert [pin for pin in pins if pin[1] != __version__] == []


def test_current_format_is_at_most_every_package_version() -> None:
    """The format is the version of the release that introduced it, so it never runs ahead of a package."""
    current = config.current_format()
    package = json.loads((REPO_ROOT / "node" / "package.json").read_text(encoding="utf-8"))["version"]
    for version in (__version__, package, _plugin_version()):
        assert config.compare_versions(current, version) <= 0, version


@pytest.fixture(scope="session")
def release_rule() -> ModuleType:
    """scripts/release_rule.py, the release rule `scripts/release-check` applies."""
    spec = importlib.util.spec_from_file_location("release_rule", REPO_ROOT / "scripts" / "release_rule.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _unreleased_bump_problem(root: Path, version: str, rule: ModuleType, *, on_actions: bool) -> str | None:
    """The release rule's problem with `version` while it has no tag; skips (fails on Actions) without a release tag."""
    tagged = subprocess.run(
        ["git", "rev-parse", "-q", "--verify", f"refs/tags/v{version}"], cwd=root, capture_output=True, check=False
    )
    if tagged.returncode == 0:
        return None
    previous = rule.previous_release(root, version)
    if previous is None:
        reason = f"no release tag below {version} is reachable; fetch the full history with tags"
        if on_actions:
            pytest.fail(reason)
        pytest.skip(reason)
    return rule.bump_problem(root, version, previous)


def test_an_unreleased_version_obeys_the_release_rule(release_rule: ModuleType) -> None:
    on_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    assert _unreleased_bump_problem(REPO_ROOT, __version__, release_rule, on_actions=on_actions) is None



def test_the_rule_is_not_applied_once_the_version_is_tagged(release_repo, release_rule: ModuleType) -> None:
    release_repo.release("0.4.0")
    release_repo.change(TOOL)
    release_repo.release("0.4.1")
    assert _unreleased_bump_problem(release_repo.root, "0.4.1", release_rule, on_actions=True) is None


def test_a_tool_change_without_a_minor_bump_fails_before_tagging(release_repo, release_rule: ModuleType) -> None:
    release_repo.release("0.4.0")
    release_repo.change(TOOL)
    release_repo.bump("0.4.1")
    problem = _unreleased_bump_problem(release_repo.root, "0.4.1", release_rule, on_actions=False)
    assert problem is not None
    assert "v0.4.0" in problem
    assert TOOL in problem


def test_a_tool_change_with_a_minor_bump_passes_before_tagging(release_repo, release_rule: ModuleType) -> None:
    release_repo.release("0.4.0")
    release_repo.change(TOOL)
    release_repo.bump("0.5.0")
    assert _unreleased_bump_problem(release_repo.root, "0.5.0", release_rule, on_actions=False) is None


def test_no_release_tag_skips_locally(release_repo, release_rule: ModuleType) -> None:
    release_repo.bump("0.4.1")
    with pytest.raises(pytest.skip.Exception):
        _unreleased_bump_problem(release_repo.root, "0.4.1", release_rule, on_actions=False)


def test_no_release_tag_fails_on_github_actions(release_repo, release_rule: ModuleType) -> None:
    release_repo.bump("0.4.1")
    with pytest.raises(pytest.fail.Exception):
        _unreleased_bump_problem(release_repo.root, "0.4.1", release_rule, on_actions=True)
