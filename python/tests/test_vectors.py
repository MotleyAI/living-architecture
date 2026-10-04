"""The shared vectors agree with the pre-restructure behaviour they were recorded from."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from living_architecture.contract import normalize


def _repo_root() -> Path:
    return next(p for p in Path(__file__).resolve().parents if (p / "shared" / "vectors").is_dir())


VECTORS = _repo_root() / "shared" / "vectors"
LA_CONFIG = Path(sys.executable).parent / "la-config"


def _load(name: str) -> dict:
    return yaml.safe_load((VECTORS / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("vector", _load("repr.yaml")["cases"], ids=lambda v: v["repr"])
def test_repr_vectors_are_python_repr(vector: dict) -> None:
    assert repr(vector["value"]) == vector["repr"]


@pytest.mark.parametrize("vector", _load("yaml.yaml")["cases"], ids=lambda v: v["name"])
def test_yaml_vectors_are_pyyaml_safe_load(vector: dict) -> None:
    value = yaml.safe_load(vector["text"])
    if "json" in vector:
        assert value == json.loads(vector["json"])
    else:
        assert repr(normalize(value)) == vector["repr"]


@pytest.mark.parametrize("vector", _load("yaml.yaml")["cases"], ids=lambda v: v["name"])
def test_yaml_vectors_carry_one_expectation(vector: dict) -> None:
    assert set(vector) - {"name", "text"} in ({"json"}, {"repr"})


@pytest.mark.parametrize("vector", _load("defaults.yaml")["cases"], ids=lambda v: v["name"])
def test_default_vectors_through_la_config_show(vector: dict, tmp_path: Path) -> None:
    if vector["config"] is not None:
        (tmp_path / "living-architecture.yaml").write_text(vector["config"], encoding="utf-8")
    out = subprocess.run([str(LA_CONFIG), "--root", str(tmp_path), "show"], capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == vector["resolved"]


@pytest.mark.parametrize("vector", _load("command-split.yaml")["cases"], ids=lambda v: v["name"])
def test_command_split_vectors_are_shlex_split(vector: dict) -> None:
    if vector.get("error"):
        with pytest.raises(ValueError):
            shlex.split(vector["text"])
    else:
        assert shlex.split(vector["text"]) == vector["words"]
