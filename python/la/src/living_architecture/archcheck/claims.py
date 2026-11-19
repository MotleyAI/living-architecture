"""claims-exist and claims-exactly-once: every unit of a language is claimed once and exists, per its facts."""

from __future__ import annotations

from living_architecture.archcheck.facts import Facts
from living_architecture.archcheck.nodes import MapElement, NodeMap, separator
from living_architecture.contract import message


def _claimed(node: MapElement, roots: list[str], facts: Facts) -> list[str]:
    """`node`'s declared units, then, when its package is a configured root, that root's top-level units."""
    if node.package not in roots:
        return node.units
    sep = separator(facts.language)
    return [*node.units, *sorted(u for u in facts.top_level_units if u.startswith(f"{node.package}{sep}"))]


def _existence_findings(node: MapElement, unit: str, facts: Facts) -> list[str]:
    fact = facts.unit(unit)
    if fact.status == "missing":
        return [message("claims-exist.unit-missing", node=node.id, unit=unit)]
    if fact.status == "ambiguous":
        return [message("claims-exist.unit-ambiguous", node=node.id, unit=unit, candidates=", ".join(fact.candidates))]
    return []


def _declared_findings(node_map: NodeMap, facts: Facts, roots: list[str]) -> list[str]:
    findings: list[str] = []
    seen: dict[str, str] = {}
    for node in node_map.language_nodes(facts.language):
        for unit in _claimed(node, roots, facts):
            if unit in node.units:
                findings += _existence_findings(node, unit, facts)
            if unit in seen:
                findings.append(
                    message("claims-exactly-once.claimed-twice", unit=unit, first=seen[unit], second=node.id)
                )
            else:
                seen[unit] = node.id
    for unit in sorted(set(facts.top_level_units) - set(seen)):
        findings.append(message("claims-exactly-once.unclaimed", unit=unit))
    return findings


def _overlap(a: str, b: str, sep: str) -> bool:
    """a and b name the same subtree, or one nests inside the other."""
    return a == b or a.startswith(b + sep) or b.startswith(a + sep)


def _derived_findings(element: MapElement, candidates: list[str], facts: Facts) -> list[str]:
    findings: list[str] = []
    sep = separator(facts.language)
    unit = str(element.unit)
    clash = next((c for c in candidates if _overlap(unit, c, sep)), None)
    if clash is not None:
        findings.append(message("claims-exactly-once.child-collides", element=element.id, unit=unit, clash=clash))
    fact = facts.unit(unit)
    if fact.status == "missing":
        findings.append(message("claims-exist.child-missing", element=element.id, unit=unit))
    elif fact.status == "ambiguous":
        findings.append(
            message("claims-exist.child-ambiguous", element=element.id, unit=unit, candidates=", ".join(fact.candidates))
        )
    return findings


def check_claims(node_map: NodeMap, facts: Facts, roots: list[str]) -> list[str]:
    """One language's declared, then model-derived units: they exist, each top-level unit is claimed once (a node on a
    configured root claims that root's), and each nests only under its own node."""
    findings = _declared_findings(node_map, facts, roots)
    nodes = node_map.language_nodes(facts.language)
    declared = sorted({unit for node in nodes for unit in node.units})
    for node in nodes:
        if node.has_elements:
            findings.append(message("claims-exist.virtual-children", node=node.id))
        candidates = [unit for unit in declared if unit != node.package]
        for element in node_map.language_derived(facts.language):
            if element.node == node.id:
                findings += _derived_findings(element, candidates, facts)
    return findings
