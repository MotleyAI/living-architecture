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


def _plugin_version() -> str:
    return json.loads((REPO_ROOT / "plugin" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))[
        "version"
    ]


def test_plugin_and_package_versions_agree() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == _plugin_version() == __version__


def test_marketplace_lists_the_plugin() -> None:
    marketplace = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    plugin = json.loads((REPO_ROOT / "plugin" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    [entry] = marketplace["plugins"]
    assert entry["name"] == plugin["name"]
    assert (REPO_ROOT / entry["source"] / ".claude-plugin" / "plugin.json").is_file()


@pytest.mark.parametrize("name", ["README.md", "LICENSE"])
def test_vendored_root_files_are_current(name: str) -> None:
    current = (PROJECT_ROOT / name).read_bytes() == (REPO_ROOT / name).read_bytes()
    assert current, f"python/{name} is stale; run scripts/sync-shared"


def test_npm_package_version_agrees() -> None:
    package = REPO_ROOT / "node" / "package.json"
    assert package.is_file(), "node/package.json is missing"
    assert json.loads(package.read_text(encoding="utf-8"))["version"] == _plugin_version() == __version__


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
