import json
import re
import tomllib
from pathlib import Path

import pytest

from living_architecture import __version__, config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PROJECT_ROOT.parent
# An install pin: `living-architecture==X` (PyPI) or `living-architecture@X` (npm).
PIN = re.compile(r"living-architecture(?:==|@)(\d[\w.+-]*)")


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
def test_vendored_root_files_are_current(name: str) -> None:
    current = (PROJECT_ROOT / name).read_bytes() == (REPO_ROOT / name).read_bytes()
    assert current, f"python/{name} is stale; run scripts/sync-shared"


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


@pytest.mark.parametrize("name", ["README.md", "LICENSE"])
def test_npm_vendored_root_files_are_current(name: str) -> None:
    vendored = REPO_ROOT / "node" / name
    current = vendored.is_file() and vendored.read_bytes() == (REPO_ROOT / name).read_bytes()
    assert current, f"node/{name} is stale; run scripts/sync-shared"


def test_current_format_is_at_most_every_package_version() -> None:
    """The format is the version of the release that introduced it, so it never runs ahead of a package."""
    current = config.current_format()
    package = json.loads((REPO_ROOT / "node" / "package.json").read_text(encoding="utf-8"))["version"]
    for version in (__version__, package, _plugin_version()):
        assert config.compare_versions(current, version) <= 0, version
