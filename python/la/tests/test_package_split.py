"""The two packages: their snapshots, entry points, la's dr surface and its message fallback."""

from __future__ import annotations

import ast
import re
from importlib.metadata import entry_points
from pathlib import Path

import pytest
import yaml
from living_architecture.contract import message

from deterministic_refactor.contract import compute_hash

REPO_ROOT = next(p for p in Path(__file__).resolve().parents if (p / "shared").is_dir() and (p / "plugin").is_dir())
SHARED = REPO_ROOT / "shared"
HASH_FILE = "CONTRACT_HASH"
SNAPSHOTS = {
    "python/dr/src/deterministic_refactor/contract/data": "dr",
    "python/la/src/living_architecture/contract/data": "la",
    "node/dr/src/contract/data": "dr",
    "node/la/src/contract/data": "la",
}
DISTRIBUTIONS = {"deterministic-refactor": "dr", "living-architecture": "la"}
DR_PUBLIC = {"contract", "config", "lang", "twin", "changes"}
_TS_IMPORT = re.compile(r"""(?:from|import)\s*\(?\s*['"]([^'"]+)['"]""")


def _tree(root: Path) -> dict[str, tuple[bool, bytes]]:
    return {
        p.relative_to(root).as_posix(): (bool(p.stat().st_mode & 0o111), p.read_bytes())
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != HASH_FILE and "__pycache__" not in p.parts
    }


@pytest.mark.parametrize(("snapshot", "package"), SNAPSHOTS.items())
def test_each_snapshot_is_its_package_contract(snapshot: str, package: str) -> None:
    root = REPO_ROOT / snapshot
    assert _tree(root) == _tree(SHARED / package), f"{snapshot} is stale; run scripts/sync-shared"
    assert (root / HASH_FILE).read_text(encoding="utf-8").strip() == compute_hash(SHARED / package)


@pytest.mark.parametrize(("distribution", "package"), DISTRIBUTIONS.items())
def test_console_scripts_equal_the_package_manifest(distribution: str, package: str) -> None:
    scripts = {ep.name for ep in entry_points(group="console_scripts") if ep.dist and ep.dist.name == distribution}
    manifest = yaml.safe_load((SHARED / package / "cli.yaml").read_text(encoding="utf-8"))["commands"]
    assert scripts == set(manifest)


def test_la_renders_a_dr_finding_through_its_fallback() -> None:
    findings = yaml.safe_load((SHARED / "dr" / "findings.yaml").read_text(encoding="utf-8"))["findings"]
    template_id, text = next((i, t) for i, t in sorted(findings.items()) if "{" not in t and "}" not in t)
    assert message(template_id) == text


def _python_dr_imports(root: Path) -> set[str]:
    modules = set()
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                modules |= {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules |= {node.module, *(f"{node.module}.{alias.name}" for alias in node.names)}
    return {m for m in modules if m.split(".")[0] == "deterministic_refactor"}


def test_python_la_imports_only_the_public_dr_modules() -> None:
    imported = _python_dr_imports(REPO_ROOT / "python" / "la" / "src")
    assert imported, "la imports nothing from deterministic_refactor"
    private = {m for m in imported if len(m.split(".")) < 2 or m.split(".")[1] not in DR_PUBLIC}
    assert private == set()


def test_node_la_imports_only_the_public_dr_modules() -> None:
    specifiers = {
        spec
        for path in (REPO_ROOT / "node" / "la" / "src").rglob("*.ts")
        for spec in _TS_IMPORT.findall(path.read_text(encoding="utf-8"))
    }
    dr = {s for s in specifiers if s.split("/")[0] == "deterministic-refactor"}
    assert dr, "node/la imports nothing from deterministic-refactor"
    assert {s for s in dr if s.removeprefix("deterministic-refactor/") not in DR_PUBLIC} == set()
    assert {s for s in specifiers if "dr/src" in s} == set()
