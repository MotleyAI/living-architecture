"""model-truth: the model's arrows equal the measured runtime import edges; `license` exposes that law."""

from __future__ import annotations

from functools import cache
from pathlib import Path

from living_architecture.archcheck.index import Layout, declared_languages, load_index
from living_architecture.archcheck.nodes import build_node_map, unit_to_element
from living_architecture.c4 import is_or_ancestor, parse_model
from living_architecture.contract import message
from living_architecture.lang import import_targets, source_modules


def _attribute(module: str, units: dict[str, str]) -> str | None:
    """The finest declared element a Python module belongs to (longest unit prefix), or None."""
    best: str | None = None
    for unit in units:
        if (module == unit or module.startswith(unit + ".")) and (best is None or len(unit) > len(best)):
            best = unit
    return units[best] if best is not None else None


def _internal(src_elem: str, dst_elem: str) -> bool:
    """Self-pairs and ancestor<->descendant pairs are internal plumbing, never governed by arrows."""
    return is_or_ancestor(src_elem, dst_elem) or is_or_ancestor(dst_elem, src_elem)


def measure_runtime_edges(layout: Layout, units: dict[str, str]) -> dict[tuple[str, str], tuple[str, str]]:
    """Element-level Python import edges -> the first witness (importing module, imported module).

    Sources and targets go in sorted module-id order; endpoints attribute to their finest declared element;
    self- and ancestor/descendant pairs drop as internal; the root package's own module is exempt.
    """
    witnesses: dict[tuple[str, str], tuple[str, str]] = {}
    for source in sorted(source_modules(layout.source_root, layout.root_package), key=lambda s: s.module):
        src_elem = _attribute(source.module, units)
        if src_elem is None:
            continue
        for target in sorted(import_targets(source)):
            dst_elem = _attribute(target, units)
            if dst_elem is None or src_elem == dst_elem or _internal(src_elem, dst_elem):
                continue
            witnesses.setdefault((src_elem, dst_elem), (source.module, target))
    return witnesses


def _covers(arrow: tuple[str, str], edge: tuple[str, str]) -> bool:
    return is_or_ancestor(arrow[0], edge[0]) and is_or_ancestor(arrow[1], edge[1])


def _more_specific(a: tuple[str, str], b: tuple[str, str]) -> bool:
    """a is strictly more specific than b: descends-from b on both endpoints, and differs."""
    return a != b and is_or_ancestor(b[0], a[0]) and is_or_ancestor(b[1], a[1])


def _arrow_is_live(arrow: tuple[str, str], edges: list[tuple[str, str]], arrows: list[tuple[str, str]]) -> bool:
    """An arrow is live iff it is a most-specific cover of at least one measured edge."""
    covered = [e for e in edges if _covers(arrow, e)]
    for edge in covered:
        rivals = [a for a in arrows if _covers(a, edge)]
        if not any(_more_specific(a, arrow) for a in rivals):
            return True
    return False


def check_model_truth(witnesses: dict[tuple[str, str], tuple[str, str]], arrows: list[tuple[str, str]]) -> list[str]:
    """Measured edges (every language's) against every arrow: missing edges sorted, then arrows in model order."""
    edges = list(witnesses)
    findings: list[str] = []
    # A parent<->child arrow would asymmetrically cover sibling edges; keep it out of coverage.
    valid = [a for a in arrows if not _internal(a[0], a[1])]
    for src, dst in arrows:
        if _internal(src, dst):
            findings.append(message("model-truth.internal-arrow", src=src, dst=dst))
    for edge in sorted(edges):
        if not any(_covers(arrow, edge) for arrow in valid):
            src_mod, dst_mod = witnesses[edge]
            findings.append(
                message("model-truth.missing-edge", src=edge[0], dst=edge[1], src_module=src_mod, dst_module=dst_mod)
            )
    for arrow in valid:
        if not any(_covers(arrow, e) for e in edges):
            findings.append(message("model-truth.dead", src=arrow[0], dst=arrow[1]))
        elif not _arrow_is_live(arrow, edges, valid):
            findings.append(message("model-truth.shadowed", src=arrow[0], dst=arrow[1]))
    return findings


@cache
def _license_model(root_str: str) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    """Cached (unit, element) pairs plus arrow set for `license`, keyed by repo root."""
    root = Path(root_str)
    model = parse_model(root)
    mapping = tuple(unit_to_element(build_node_map(model, declared_languages(load_index(root))), "python").items())
    arrows = tuple((r.src, r.dst) for r in model.relations if not _internal(r.src, r.dst))
    return mapping, arrows


def license(*, root: Path, src: str, dst: str) -> bool:
    """Whether the model licenses a runtime import from Python module `src` to Python module `dst`.

    Internal and unmodelled endpoints are never banned; otherwise a declared arrow must cover the edge.
    """
    mapping, arrows = _license_model(str(root))
    units = dict(mapping)
    src_elem = _attribute(src, units)
    dst_elem = _attribute(dst, units)
    if src_elem is None or dst_elem is None or _internal(src_elem, dst_elem):
        return True
    return any(_covers(arrow, (src_elem, dst_elem)) for arrow in arrows)
