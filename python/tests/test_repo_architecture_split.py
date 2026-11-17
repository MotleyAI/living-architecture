"""This repo's architecture model splits each language root into dr and la, with la -> dr the only cross arrow."""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir())
ARCHITECTURE = REPO_ROOT / "architecture"
MODEL = (ARCHITECTURE / "model.c4").read_text(encoding="utf-8")
RELATION = re.compile(r"^\s*([\w.]+)\s*-\[?[\w#]*\]?->\s*([\w.]+)", re.MULTILINE)


def _index() -> dict[str, Any]:
    return yaml.safe_load((ARCHITECTURE / "index.yaml").read_text(encoding="utf-8"))


def test_index_maps_the_packages_per_language() -> None:
    index = _index()
    assert index["python"] == {
        "source_roots": ["python/dr/src", "python/la/src"],
        "root_packages": ["deterministic_refactor", "living_architecture"],
    }
    assert {k: v for k, v in index["typescript"].items() if k != "tsconfig"} == {
        "source_root": "node",
        "root_packages": ["dr/src", "la/src"],
    }


def test_doctor_spec_touches_both_doctors() -> None:
    assert _index()["cross_cutting_specs"]["doctor"] == {"touches": ["python.dr.doctor", "python.la.doctor"]}


@pytest.mark.parametrize(
    ("root", "dr_package", "la_package"),
    [("python", "deterministic_refactor", "living_architecture"), ("typescript", "dr/src", "la/src")],
)
def test_each_root_has_a_dr_and_an_la_node(root: str, dr_package: str, la_package: str) -> None:
    body = MODEL.split(f"{root} = system", 1)[1]
    dr = re.search(r"^    dr = node 'deterministic-refactor' \{\s*metadata \{\s*package '([^']+)'", body, re.MULTILINE)
    la = re.search(r"^    la = node 'living-architecture' \{\s*metadata \{\s*package '([^']+)'", body, re.MULTILINE)
    assert dr and dr.group(1) == dr_package
    assert la and la.group(1) == la_package


def test_la_to_dr_is_the_only_cross_package_arrow() -> None:
    def package(endpoint: str) -> str:
        return endpoint.split(".")[0]

    cross = [(s, t) for s, t in RELATION.findall(MODEL) if {package(s), package(t)} == {"dr", "la"}]
    assert sorted(cross) == [("la", "dr"), ("la", "dr")]
