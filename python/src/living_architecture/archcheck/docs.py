"""arc42-exists, spec-mapping and baseline-ratchet (all read from the repo root)."""

from __future__ import annotations

from pathlib import Path

from living_architecture.archcheck.nodes import NodeMap
from living_architecture.contract import message

SYSTEM_DOC = "architecture/system.arc42.md"


def check_arc42(root: Path, index: dict, node_map: NodeMap) -> list[str]:
    findings: list[str] = []
    if not (root / SYSTEM_DOC).is_file():
        findings.append(message("arc42-exists.system-missing", doc=SYSTEM_DOC))
    registered = {SYSTEM_DOC}
    for node in node_map.nodes:
        if node.arc42:
            registered.add(node.arc42)
            if not (root / node.arc42).is_file():
                findings.append(message("arc42-exists.node-doc-missing", node=node.id, doc=node.arc42))
    for entry in index.get("cross_cutting_arc42", []):
        registered.add(entry)
        if not (root / entry).is_file():
            findings.append(message("arc42-exists.cross-cutting-missing", doc=entry))
    for path in sorted((root / "architecture").glob("*.arc42.md")):
        rel = f"architecture/{path.name}"
        if rel not in registered:
            findings.append(message("arc42-exists.orphan", doc=rel, system=SYSTEM_DOC))
    return findings


def _mapped_spec_groups(index: dict, node_map: NodeMap, findings: list[str]) -> dict[str, str]:
    """Spec group -> owning node (or cross_cutting_specs), appending duplicate-mapping findings."""
    nodes = node_map.node_ids()
    mapped: dict[str, str] = {}
    for node in node_map.nodes:
        for group in node.specs:
            if group in mapped:
                findings.append(message("spec-mapping.mapped-twice", group=group, first=mapped[group], second=node.id))
            mapped[group] = node.id
    for group, spec in index.get("cross_cutting_specs", {}).items():
        if group in mapped:
            findings.append(
                message("spec-mapping.mapped-twice", group=group, first=mapped[group], second="cross_cutting_specs")
            )
        mapped[group] = "cross_cutting_specs"
        for touched in spec.get("touches", []):
            if touched not in nodes:
                findings.append(message("spec-mapping.unknown-node", group=group, node=touched))
    return mapped


def _subdirs(path: Path) -> list[Path]:
    return [p for p in path.iterdir() if p.is_dir()] if path.is_dir() else []


def _present_spec_groups(root: Path) -> dict[str, list[Path]]:
    """Spec group -> its dirs under openspec/specs/ and every non-archived change's specs/."""
    openspec = root / "openspec"
    specs_dirs = [openspec / "specs"]
    specs_dirs += [change / "specs" for change in _subdirs(openspec / "changes") if change.name != "archive"]
    present: dict[str, list[Path]] = {}
    for specs_dir in specs_dirs:
        for group_dir in _subdirs(specs_dir):
            present.setdefault(group_dir.name, []).append(group_dir)
    return present


def check_spec_mapping(root: Path, index: dict, node_map: NodeMap) -> list[str]:
    findings: list[str] = []
    mapped = _mapped_spec_groups(index, node_map, findings)
    present = _present_spec_groups(root)
    for group in sorted(set(present) - set(mapped)):
        findings.append(message("spec-mapping.unmapped", group=group))
    for group in sorted(set(mapped) - set(present)):
        findings.append(message("spec-mapping.dir-missing", group=group))
    for group in sorted(set(mapped) & set(present)):
        if not any(any(group_dir.rglob("spec.md")) for group_dir in present[group]):
            findings.append(message("spec-mapping.no-spec-md", group=group))
    return findings


def check_legacy_ratchet(index: dict, arrows_legacy: int) -> list[str]:
    """The count of `#legacy` arrows in the model must equal the declared baseline (only ever lowered)."""
    spec = index.get("legacy_arrows")
    if not isinstance(spec, dict) or "baseline" not in spec:
        return [message("baseline-ratchet.missing")]
    baseline = spec["baseline"]
    if not isinstance(baseline, int) or isinstance(baseline, bool) or baseline < 0:
        return [message("baseline-ratchet.invalid", value=baseline)]
    if arrows_legacy != baseline:
        return [message("baseline-ratchet.mismatch", count=arrows_legacy, baseline=baseline)]
    return []
