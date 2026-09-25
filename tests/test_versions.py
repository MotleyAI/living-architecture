import json
import tomllib
from pathlib import Path

from living_architecture import __version__

REPO_ROOT = Path(__file__).resolve().parent.parent


def _plugin_version() -> str:
    return json.loads((REPO_ROOT / "plugin" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))[
        "version"
    ]


def test_plugin_and_package_versions_agree() -> None:
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == _plugin_version() == __version__


def test_marketplace_lists_the_plugin() -> None:
    marketplace = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    plugin = json.loads((REPO_ROOT / "plugin" / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    [entry] = marketplace["plugins"]
    assert entry["name"] == plugin["name"]
    assert (REPO_ROOT / entry["source"] / ".claude-plugin" / "plugin.json").is_file()
