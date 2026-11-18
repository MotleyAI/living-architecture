"""The shared contract split per package: shared/dr and shared/la, their manifests, schemas, registries and formats."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir())
SHARED = REPO_ROOT / "shared"
DR_FILE = "deterministic-refactor.yaml"
LA_FILE = "living-architecture.yaml"
DR_SCHEMA = "deterministic-refactor.schema.json"
DR_KEYS = {"format", "exempt", "commands", "refactor"}
DR_COMMANDS = {"dr-refactor", "dr-compliance", "dr-mock-lint", "dr-typecheck", "dr-doctor", "dr-config"}
REVIEW_SHIMS = {
    "la-fetch-coderabbit-threads", "la-fetch-failed-pr-checks", "la-pr-reviewers", "la-reply-invalid-coderabbit",
    "la-reply-to-pr-thread", "la-wait-for-reviews",
}
_VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")


def _yaml(rel: str) -> dict[str, Any]:
    return yaml.safe_load((SHARED / rel).read_text(encoding="utf-8"))


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _commands(package: str) -> dict[str, Any]:
    return _yaml(f"{package}/cli.yaml")["commands"]


def _version_key(version: str) -> tuple[int, ...]:
    match = _VERSION.fullmatch(version)
    assert match, version
    return tuple(int(part) for part in match.groups())


def test_shared_holds_only_the_package_contracts() -> None:
    assert sorted(p.name for p in SHARED.iterdir()) == ["dr", "la"]


@pytest.mark.parametrize("package", ["dr", "la"])
def test_each_contract_has_its_manifest_registry_and_readme(package: str) -> None:
    for rel in ("cli.yaml", "findings.yaml", "README.md"):
        assert (SHARED / package / rel).is_file(), f"shared/{package}/{rel}"


def test_dr_manifest_defines_exactly_the_dr_commands() -> None:
    assert set(_commands("dr")) == DR_COMMANDS


def test_la_manifest_defines_only_la_commands() -> None:
    commands = set(_commands("la"))
    assert all(name.startswith("la-") for name in commands), commands
    assert {"la-typecheck", "la-doctor", "la-config", "la-arch-check"} <= commands


def test_format_exempt_commands() -> None:
    exempt = {
        name for package in ("dr", "la") for name, spec in _commands(package).items() if spec.get("format") == "exempt"
    }
    assert exempt == {"la-arch-migrate", "la-doctor", "dr-doctor", *REVIEW_SHIMS}


def test_dr_commands_native_languages() -> None:
    native = {name: spec["native"] for name, spec in _commands("dr").items() if "native" in spec}
    assert native == {name: ["python", "typescript"] for name in ("dr-refactor", "dr-compliance", "dr-mock-lint")}
    assert not any("native" in spec for spec in _commands("la").values())


def test_dr_config_lists_the_config_files_and_their_formats() -> None:
    config = _yaml("dr/config.yaml")
    assert config["files"] == [DR_FILE, LA_FILE]
    assert config["formats"] == {DR_FILE: ["0.13.0"], LA_FILE: ["0.4.0", "0.13.0"]}


def _package_versions() -> dict[str, str]:
    versions = {
        f"python/{package}/pyproject.toml": tomllib.loads(
            (REPO_ROOT / "python" / package / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]["version"]
        for package in ("dr", "la")
    }
    versions |= {f"node/{p}/package.json": _json(REPO_ROOT / "node" / p / "package.json")["version"] for p in ("dr", "la")}
    versions |= {
        f"plugin/{p}/.claude-plugin/plugin.json": _json(REPO_ROOT / "plugin" / p / ".claude-plugin" / "plugin.json")["version"]
        for p in ("dr", "la")
    }
    return versions


@pytest.mark.parametrize("file", [DR_FILE, LA_FILE])
def test_released_formats_are_well_formed(file: str) -> None:
    formats = _yaml("dr/config.yaml")["formats"][file]
    keys = [_version_key(version) for version in formats]
    assert keys and keys == sorted(set(keys))
    for where, version in _package_versions().items():
        assert keys[-1] <= _version_key(version), where


def _schema(package: str, name: str) -> dict[str, Any]:
    return _json(SHARED / package / "schema" / name)


def test_dr_schema_defines_exactly_the_dr_keys() -> None:
    schema = _schema("dr", DR_SCHEMA)
    assert schema["$id"] == DR_SCHEMA
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == DR_KEYS
    assert next(iter(schema["properties"])) == "format"
    commands = schema["properties"]["commands"]
    assert set(commands["properties"]) == {"test", "typecheck"}
    assert commands["additionalProperties"] is False
    exempt = schema["properties"]["exempt"]
    assert (exempt["type"], exempt["items"]["type"], exempt["default"]) == ("array", "string", [])
    fmt = schema["properties"]["format"]
    assert (fmt["type"], fmt["default"], fmt["pattern"][0], fmt["pattern"][-1]) == (["string", "null"], None, "^", "$")
    typecheck = commands["properties"]["typecheck"]
    defaults = {name: spec.get("default") for name, spec in typecheck["properties"].items()}
    assert defaults == {"python": "basedpyright", "typescript": "tsc --noEmit"}
    assert typecheck["additionalProperties"] is False


def test_la_schema_takes_the_dr_keys_by_reference() -> None:
    schema = _schema("la", "living-architecture.schema.json")
    assert schema["additionalProperties"] is False
    assert "allOf" not in schema
    properties = schema["properties"]
    for key in ("format", "exempt", "refactor"):
        assert properties[key] == {"$ref": f"{DR_SCHEMA}#/properties/{key}"}, key
    commands = properties["commands"]
    assert commands["additionalProperties"] is False
    for key in ("test", "typecheck"):
        assert commands["properties"][key] == {"$ref": f"{DR_SCHEMA}#/properties/commands/properties/{key}"}, key
    assert "$ref" not in commands["properties"]["lint"]


def test_la_schema_retires_the_nested_exempt() -> None:
    conventions = _schema("la", "living-architecture.schema.json")["properties"]["conventions"]
    assert "exempt" not in conventions["properties"]
    assert conventions["additionalProperties"] is False


def test_finding_ids_are_unique_across_the_packages() -> None:
    dr, la = (set(_yaml(f"{package}/findings.yaml")["findings"]) for package in ("dr", "la"))
    assert dr & la == set()
