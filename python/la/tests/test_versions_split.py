"""Both packages and both plugins move in lockstep, and la pins dr to its own minor."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

import deterministic_refactor
import living_architecture

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
        "python/dr/pyproject.toml": _project("dr")["version"],
        "python/la/pyproject.toml": _project("la")["version"],
        "node/dr/package.json": _json("node/dr/package.json")["version"],
        "node/la/package.json": _json("node/la/package.json")["version"],
        "plugin/dr/.claude-plugin/plugin.json": _json("plugin/dr/.claude-plugin/plugin.json")["version"],
        "plugin/la/.claude-plugin/plugin.json": _json("plugin/la/.claude-plugin/plugin.json")["version"],
        "deterministic_refactor.__version__": deterministic_refactor.__version__,
    }
    assert {where: v for where, v in versions.items() if v != living_architecture.__version__} == {}


def test_package_names() -> None:
    assert (_project("dr")["name"], _project("la")["name"]) == ("deterministic-refactor", "living-architecture")
    assert _json("node/dr/package.json")["name"] == "deterministic-refactor"
    assert _json("node/la/package.json")["name"] == "living-architecture"


def test_python_la_pins_dr_to_its_minor() -> None:
    base, upper = _series()
    assert f"deterministic-refactor>={base},<{upper}" in _project("la")["dependencies"]
    assert not any(dep.startswith("living-architecture") for dep in _project("dr")["dependencies"])


def test_npm_la_pins_dr_to_its_minor() -> None:
    base, _ = _series()
    assert _json("node/la/package.json")["dependencies"]["deterministic-refactor"] == f"~{base}"
    assert "living-architecture" not in _json("node/dr/package.json").get("dependencies", {})


def test_la_plugin_depends_on_the_dr_plugin() -> None:
    base, _ = _series()
    assert _json("plugin/la/.claude-plugin/plugin.json")["dependencies"] == [{"name": "dr", "version": f"~{base}"}]
    assert "dependencies" not in _json("plugin/dr/.claude-plugin/plugin.json")


def test_marketplace_lists_both_plugins() -> None:
    entries = {entry["name"]: entry["source"] for entry in _json(".claude-plugin/marketplace.json")["plugins"]}
    assert entries == {"dr": "./plugin/dr", "la": "./plugin/la"}
    for source in entries.values():
        assert (REPO_ROOT / source / ".claude-plugin" / "plugin.json").is_file()
