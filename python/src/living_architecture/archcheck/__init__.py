"""Living-architecture cross-walk checker: code, LikeC4 model, arc42 docs and specs agree."""

from __future__ import annotations

import sys
from pathlib import Path

from living_architecture.archcheck.claims import check_children, check_claims, node_claims
from living_architecture.archcheck.docs import (
    check_arc42,
    check_legacy_ratchet,
    check_model_identity,
    check_spec_mapping,
)
from living_architecture.archcheck.index import ArchCheckError, Layout, load_index, resolve_layout
from living_architecture.archcheck.tags import check_enforced_tags
from living_architecture.archcheck.truth import (
    check_model_truth,
    license,
    measure_runtime_edges,
    unit_to_element,
)
from living_architecture.c4 import check_diagrams_fresh, parse_model, parse_views
from living_architecture.config import ConfigError, load_config
from living_architecture.contract import message

__all__ = [
    "ArchCheckError",
    "Layout",
    "license",
    "measure_runtime_edges",
    "resolve_layout",
    "run",
    "run_checks",
    "unit_to_element",
]


def _findings(root: Path) -> list[str]:
    index = load_index(root)
    layout = resolve_layout(root, index)
    nodes = index.get("nodes", {})
    model = parse_model(root)
    views = parse_views(root=root, model=model)
    elements = {e.id for e in model.elements}
    arrows = [(r.src, r.dst) for r in model.relations]
    legacy_count = sum(1 for r in model.relations if r.legacy)
    findings: list[str] = []
    findings += check_claims(layout, node_claims(nodes))
    findings += check_children(layout, nodes)
    findings += check_arc42(root, index)
    findings += check_model_identity(nodes=nodes, elements=elements)
    findings += check_spec_mapping(root, index)
    findings += check_legacy_ratchet(index, legacy_count)
    findings += check_model_truth(layout=layout, nodes=nodes, arrows=arrows)
    findings += check_enforced_tags(root, load_config(root).issue_key_re())
    findings += check_diagrams_fresh(root=root, model=model, views=views)
    return findings


def run_checks(root: Path) -> list[str]:
    """Every finding for the repo at `root`; ArchCheckError when the setup is too broken to check."""
    try:
        return _findings(root)
    except OSError as exc:
        raise ArchCheckError(str(exc)) from exc


def run(root: Path) -> int:
    """`la-arch-check`: print the findings and a summary."""
    try:
        findings = run_checks(root)
    except (ArchCheckError, ConfigError) as exc:
        print(message("arch-check.setup-error", error=str(exc)), file=sys.stderr)
        return 2
    for finding in findings:
        print(finding)
    if findings:
        print(message("arch-check.summary", count=len(findings)))
        return 1
    print(message("arch-check.ok"))
    return 0
