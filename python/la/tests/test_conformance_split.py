"""The conformance corpus split per package: one case tree and inventory each, shared fixtures, own commands only."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from test_contract import _produced_ids

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir())
CORPUS = REPO_ROOT / "conformance"
PACKAGES = ("trmv", "la")
UNPRODUCED_BY_DESIGN = {
    "trmv": {"refactor.conflicting-edits", "refactor.rope-walk", "compliance.rope-walk", "refactor.file-changed"},
    "la": {"arch-migrate.rollback-failed"},
}


def _cases(package: str) -> list[Path]:
    return sorted(p.parent for p in (CORPUS / package / "cases").glob("*/case.yaml"))


def _manifest(package: str) -> set[str]:
    return set(yaml.safe_load((REPO_ROOT / "shared" / package / "cli.yaml").read_text(encoding="utf-8"))["commands"])


def _case(case_dir: Path) -> dict[str, Any]:
    return yaml.safe_load((case_dir / "case.yaml").read_text(encoding="utf-8"))


def test_corpus_holds_the_two_trees_and_the_shared_fixtures() -> None:
    assert sorted(p.name for p in CORPUS.iterdir() if p.is_dir()) == ["fixtures", "la", "trmv"]
    for package in PACKAGES:
        assert _cases(package), package
        assert (CORPUS / package / "INVENTORY.md").is_file(), package


@pytest.mark.parametrize("package", PACKAGES)
def test_inventory_lists_exactly_its_trees_cases(package: str) -> None:
    listed = set(re.findall(r"`([a-z0-9-]+)`", (CORPUS / package / "INVENTORY.md").read_text(encoding="utf-8")))
    cases = {p.name for p in _cases(package)}
    assert cases - listed == set(), "cases missing from the inventory"
    other = {p.name for other in PACKAGES if other != package for p in _cases(other)}
    assert listed & other == set(), "the inventory lists the other tree's cases"


def test_case_ids_are_unique_across_the_trees() -> None:
    trmv, la = ({p.name for p in _cases(package)} for package in PACKAGES)
    assert trmv & la == set()


@pytest.mark.parametrize("package", PACKAGES)
def test_cases_invoke_only_their_packages_commands(package: str) -> None:
    foreign = [p.name for p in _cases(package) if _case(p)["command"] not in _manifest(package)]
    assert foreign == []


@pytest.mark.parametrize("package", PACKAGES)
def test_fixtures_named_by_cases_exist_in_the_shared_directory(package: str) -> None:
    fixtures: set[str] = {f for p in _cases(package) if (f := _case(p).get("fixture"))}
    assert {f for f in fixtures if not (CORPUS / "fixtures" / f).is_dir()} == set()


def _golden_records(package: str) -> list[str]:
    tree = CORPUS / package / "cases"
    records = [p.read_text(encoding="utf-8") for p in tree.rglob("*") if p.is_file() and p.parent.name != "repo"
               and (p.name.startswith(("stdout", "stderr")) or "files" in p.relative_to(tree).parts[1:2])]
    for case_dir in _cases(package):
        expect = _case(case_dir)["expect"]
        records += [n for stream in ("stdout", "stderr") if isinstance(expect.get(stream), dict)
                    for n in expect[stream]["contains"]]
    return records


@pytest.mark.parametrize("package", PACKAGES)
def test_every_registry_template_is_produced_by_its_corpus(package: str) -> None:
    registry = yaml.safe_load((REPO_ROOT / "shared" / package / "findings.yaml").read_text(encoding="utf-8"))["findings"]
    unproduced = set(registry) - _produced_ids(registry, _golden_records(package))
    assert sorted(unproduced) == sorted(UNPRODUCED_BY_DESIGN[package])
