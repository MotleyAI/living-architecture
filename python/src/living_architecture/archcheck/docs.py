"""arc42-exists, model-identity, spec-mapping and baseline-ratchet (all read from the repo root)."""

from __future__ import annotations

from pathlib import Path

from living_architecture.contract import message

SYSTEM_DOC = "architecture/system.arc42.md"


def check_arc42(root: Path, index: dict) -> list[str]:
    findings: list[str] = []
    if not (root / SYSTEM_DOC).is_file():
        findings.append(message("arc42-exists.system-missing", doc=SYSTEM_DOC))
    registered = {SYSTEM_DOC}
    for node_id, spec in index.get("nodes", {}).items():
        arc42 = spec.get("arc42")
        if arc42:
            registered.add(arc42)
            if not (root / arc42).is_file():
                findings.append(message("arc42-exists.node-doc-missing", node=node_id, doc=arc42))
    for entry in index.get("cross_cutting_arc42", []):
        registered.add(entry)
        if not (root / entry).is_file():
            findings.append(message("arc42-exists.cross-cutting-missing", doc=entry))
    for path in sorted((root / "architecture").glob("*.arc42.md")):
        rel = f"architecture/{path.name}"
        if rel not in registered:
            findings.append(message("arc42-exists.orphan", doc=rel, system=SYSTEM_DOC))
    return findings


def _declared_children(nodes: dict) -> set[str]:
    return {f"{node_id}.{child}" for node_id, spec in nodes.items() for child in spec.get("children", [])}


def check_model_identity(nodes: dict, elements: set[str]) -> list[str]:
    findings: list[str] = []
    children = _declared_children(nodes)
    for node_id in nodes:
        if node_id not in elements:
            findings.append(message("model-identity.node", node=node_id))
    for child in sorted(children):
        if child not in elements:
            findings.append(message("model-identity.child", child=child))
    for element in sorted(elements - set(nodes) - children):
        findings.append(message("model-identity.element", element=element))
    return findings


def _mapped_spec_groups(index: dict, findings: list[str]) -> dict[str, str]:
    """Spec group -> owning node (or cross_cutting_specs), appending duplicate-mapping findings."""
    nodes = index.get("nodes", {})
    mapped: dict[str, str] = {}
    for node_id, spec in nodes.items():
        for group in spec.get("specs", []):
            if group in mapped:
                findings.append(message("spec-mapping.mapped-twice", group=group, first=mapped[group], second=node_id))
            mapped[group] = node_id
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


def check_spec_mapping(root: Path, index: dict) -> list[str]:
    findings: list[str] = []
    mapped = _mapped_spec_groups(index, findings)
    specs_dir = root / "openspec" / "specs"
    on_disk = {p.name for p in specs_dir.iterdir() if p.is_dir()} if specs_dir.is_dir() else set()
    for group in sorted(on_disk - set(mapped)):
        findings.append(message("spec-mapping.unmapped", group=group))
    for group in sorted(set(mapped) - on_disk):
        findings.append(message("spec-mapping.dir-missing", group=group))
    for group in sorted(set(mapped) & on_disk):
        if not any((specs_dir / group).rglob("spec.md")):
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
