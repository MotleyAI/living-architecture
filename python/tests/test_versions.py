import json
import tomllib
from pathlib import Path

import pytest

from living_architecture import __version__

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PROJECT_ROOT.parent


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
