"""claims-exist and claims-exactly-once: every unit is claimed once and exists under the source root."""

from __future__ import annotations

from living_architecture.archcheck.index import Layout
from living_architecture.archcheck.nodes import Derived, NodeMap
from living_architecture.contract import message
from living_architecture.lang import top_level_units, unit_exists


def _declared_findings(layout: Layout, node_map: NodeMap) -> list[str]:
    findings: list[str] = []
    seen: dict[str, str] = {}
    for node in node_map.nodes:
        for unit in node.units:
            if not unit_exists(layout.source_root, unit):
                findings.append(message("claims-exist.unit-missing", node=node.id, unit=unit))
            if unit in seen:
                findings.append(
                    message("claims-exactly-once.claimed-twice", unit=unit, first=seen[unit], second=node.id)
                )
            else:
                seen[unit] = node.id
    unclaimed = top_level_units(layout.source_root, layout.root_package) - set(seen)
    for unit in sorted(unclaimed):
        findings.append(message("claims-exactly-once.unclaimed", unit=unit))
    return findings


def _overlap(a: str, b: str) -> bool:
    """a and b name the same subtree, or one nests inside the other."""
    return a == b or a.startswith(b + ".") or b.startswith(a + ".")


def _derived_findings(layout: Layout, element: Derived, candidates: list[str]) -> list[str]:
    findings: list[str] = []
    clash = next((c for c in candidates if _overlap(element.unit, c)), None)
    if clash is not None:
        findings.append(
            message("claims-exactly-once.child-collides", element=element.id, unit=element.unit, clash=clash)
        )
    if not unit_exists(layout.source_root, element.unit):
        findings.append(message("claims-exist.child-missing", element=element.id, unit=element.unit))
    return findings


def check_claims(layout: Layout, node_map: NodeMap) -> list[str]:
    """Declared units, then model-derived units: they exist, and each nests only under its own node."""
    findings = _declared_findings(layout, node_map)
    declared = sorted({unit for node in node_map.nodes for unit in node.units})
    for node in node_map.nodes:
        if node.has_elements:
            findings.append(message("claims-exist.virtual-children", node=node.id))
        candidates = [unit for unit in declared if unit != node.package]
        for element in node_map.derived:
            if element.node == node.id:
                findings += _derived_findings(layout, element, candidates)
    return findings
