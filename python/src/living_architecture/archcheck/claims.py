"""claims-exist and claims-exactly-once: every unit is claimed once and exists under the source root."""

from __future__ import annotations

from pathlib import Path

from living_architecture.archcheck.index import Layout
from living_architecture.contract import message
from living_architecture.lang import top_level_units, unit_exists


def node_claims(nodes: dict) -> dict[str, list[str]]:
    """Node id -> units it claims (package + loose claims, or bucket packages)."""
    claims: dict[str, list[str]] = {}
    for node_id, spec in nodes.items():
        if spec.get("virtual"):
            claims[node_id] = list(spec.get("packages", []))
        else:
            claims[node_id] = [spec["package"], *spec.get("claims", [])]
    return claims


def check_claims(layout: Layout, claims: dict[str, list[str]]) -> list[str]:
    findings: list[str] = []
    seen: dict[str, str] = {}
    for node_id, units in claims.items():
        for unit in units:
            if not unit_exists(layout.source_root, unit):
                findings.append(message("claims-exist.unit-missing", node=node_id, unit=unit))
            if unit in seen:
                findings.append(
                    message("claims-exactly-once.claimed-twice", unit=unit, first=seen[unit], second=node_id)
                )
            else:
                seen[unit] = node_id
    unclaimed = top_level_units(layout.source_root, layout.root_package) - set(seen)
    for unit in sorted(unclaimed):
        findings.append(message("claims-exactly-once.unclaimed", unit=unit))
    return findings


def _package_units(nodes: dict) -> set[str]:
    """Every package/claim a node owns (for cross-node child collision detection)."""
    units: set[str] = set()
    for spec in nodes.values():
        if spec.get("virtual"):
            units.update(spec.get("packages", []))
        else:
            units.add(spec["package"])
            units.update(spec.get("claims", []))
    return units


def _overlap(a: str, b: str) -> bool:
    """a and b name the same subtree, or one nests inside the other."""
    return a == b or a.startswith(b + ".") or b.startswith(a + ".")


def _child_collision(unit: str, package: str, owned: set[str]) -> str | None:
    """The declared unit a child overlaps, or None. A child nests only under its own node's package;
    overlapping any other package/claim would split it across nodes."""
    for other in owned:
        if other != package and _overlap(unit, other):
            return other
    return None


def _node_child_findings(
    source_root: Path, node_id: str, package: str, children: list[str], owned: set[str]
) -> list[str]:
    findings: list[str] = []
    seen: set[str] = set()
    for child in children:
        unit = f"{package}.{child}"
        if child in seen:
            findings.append(message("claims-exactly-once.child-twice", node=node_id, child=child))
        seen.add(child)
        clash = _child_collision(unit=unit, package=package, owned=owned)
        if clash is not None:
            findings.append(
                message("claims-exactly-once.child-collides", node=node_id, child=child, unit=unit, clash=clash)
            )
        if not unit_exists(source_root, unit):
            findings.append(message("claims-exist.child-missing", node=node_id, child=child))
    return findings


def check_children(layout: Layout, nodes: dict) -> list[str]:
    """Declared children exist under their node's package, are named once, and overlap no other node."""
    findings: list[str] = []
    owned = _package_units(nodes)
    for node_id, spec in nodes.items():
        children = spec.get("children", [])
        if not children:
            continue
        if spec.get("virtual"):
            findings.append(message("claims-exist.virtual-children", node=node_id))
            continue
        findings += _node_child_findings(
            source_root=layout.source_root, node_id=node_id, package=spec["package"], children=children, owned=owned
        )
    return findings
