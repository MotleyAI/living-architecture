"""Both packages and both plugins move in lockstep, and la pins trmv to its own minor."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

import living_architecture
import trmv

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir())


def _json(rel: str) -> dict[str, Any]:
    return json.loads((REPO_ROOT / rel).read_text(encoding="utf-8"))


def _project(package: str) -> dict[str, Any]:
    return tomllib.loads((REPO_ROOT / "python" / package / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def _series() -> tuple[str, str]:
    major, minor = living_architecture.__version__.split(".")[:2]
    return f"{major}.{minor}.0", f"{major}.{int(minor) + 1}"


def test_every_version_agrees() -> None:
    versions = {
        "python/trmv/pyproject.toml": _project("trmv")["version"],
        "python/la/pyproject.toml": _project("la")["version"],
        "node/trmv/package.json": _json("node/trmv/package.json")["version"],
        "node/la/package.json": _json("node/la/package.json")["version"],
        "plugin/trmv/.claude-plugin/plugin.json": _json("plugin/trmv/.claude-plugin/plugin.json")["version"],
        "plugin/la/.claude-plugin/plugin.json": _json("plugin/la/.claude-plugin/plugin.json")["version"],
        "trmv.__version__": trmv.__version__,
    }
    assert {where: v for where, v in versions.items() if v != living_architecture.__version__} == {}


def test_package_names() -> None:
    assert (_project("trmv")["name"], _project("la")["name"]) == ("type-rename-move", "living-architecture")
    assert _json("node/trmv/package.json")["name"] == "type-rename-move"
    assert _json("node/la/package.json")["name"] == "living-architecture"


def test_python_la_pins_trmv_to_its_minor() -> None:
    base, upper = _series()
    assert f"type-rename-move>={base},<{upper}" in _project("la")["dependencies"]
    assert not any(dep.startswith("living-architecture") for dep in _project("trmv")["dependencies"])


def test_npm_la_pins_trmv_to_its_minor() -> None:
    base, _ = _series()
    assert _json("node/la/package.json")["dependencies"]["type-rename-move"] == f"~{base}"
    assert "living-architecture" not in _json("node/trmv/package.json").get("dependencies", {})


def test_la_plugin_depends_on_the_trmv_plugin() -> None:
    base, _ = _series()
    assert _json("plugin/la/.claude-plugin/plugin.json")["dependencies"] == [{"name": "trmv", "version": f"~{base}"}]
    assert "dependencies" not in _json("plugin/trmv/.claude-plugin/plugin.json")


def test_marketplace_lists_both_plugins() -> None:
    entries = {entry["name"]: entry["source"] for entry in _json(".claude-plugin/marketplace.json")["plugins"]}
    assert entries == {"trmv": "./plugin/trmv", "la": "./plugin/la"}
    for source in entries.values():
        assert (REPO_ROOT / source / ".claude-plugin" / "plugin.json").is_file()


KEYWORDS = {"rename", "move", "refactor", "refactoring", "typecheck", "python", "typescript", "verified", "imports"}


def test_trmv_manifests_carry_the_search_keywords() -> None:
    assert KEYWORDS <= set(_project("trmv")["keywords"])
    assert KEYWORDS <= set(_json("node/trmv/package.json")["keywords"])
