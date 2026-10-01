"""Deterministic mermaid rendering of a view."""

from __future__ import annotations

from living_architecture.c4.model import Element, ModelParse
from living_architecture.c4.views import View
from living_architecture.contract import message


def _mangle(eid: str) -> str:
    return eid.replace(".", "__")


def _escape_title(title: str) -> str:
    return title.replace('"', "#quot;")


def _node_line(element: Element | None, nid: str, indent: int) -> str:
    title = _escape_title(element.title if element else nid)
    shape = f'("{title}")' if element is not None and element.virtual else f'["{title}"]'
    return f"{' ' * indent}{_mangle(nid)}{shape}"


def render_mermaid(view: View, model: ModelParse) -> str:
    """Nested subgraphs when children are shown, else flat."""
    by_id = {e.id: e for e in model.elements}
    shown = set(view.node_ids)
    shown_kids: dict[str, list[str]] = {}
    for e in model.elements:
        if e.id in shown and e.parent in shown:
            shown_kids.setdefault(e.parent, []).append(e.id)
    lines = ["```mermaid", "flowchart TD", f"  %% {view.id}: {view.title}"]
    if any(shown_kids.values()):
        lines += _hierarchical_body(view=view, by_id=by_id, shown=shown, shown_kids=shown_kids)
    else:
        for nid in view.node_ids:
            lines.append(_node_line(element=by_id.get(nid), nid=nid, indent=2))
        for edge in view.edges:
            lines.append(f"  {edge.src} {'-.->' if edge.legacy else '-->'} {edge.dst}")
    lines.append("```")
    if any(edge.legacy for edge in view.edges):
        lines.append(message("c4.legacy-legend"))
    return "\n".join(lines)


def _hierarchical_body(
    view: View, by_id: dict[str, Element], shown: set[str], shown_kids: dict[str, list[str]]
) -> list[str]:
    lines: list[str] = []
    leaves: list[str] = []

    def emit(nid: str, indent: int) -> None:
        pad = " " * indent
        if shown_kids.get(nid):
            lines.append(f'{pad}subgraph {_mangle(nid)}["{_escape_title(by_id[nid].title)}"]')
            for child in shown_kids[nid]:
                emit(child, indent + 2)
            lines.append(f"{pad}end")
        else:
            leaves.append(_mangle(nid))
            lines.append(_node_line(element=by_id.get(nid), nid=nid, indent=indent))

    for eid in view.node_ids:
        element = by_id.get(eid)
        if element is None or element.parent not in shown:
            emit(eid, 2)
    for edge in view.edges:
        lines.append(f"  {_mangle(edge.src)} {'-.->' if edge.legacy else '-->'} {_mangle(edge.dst)}")
    if leaves:
        lines.append("  classDef leaf fill:none;")
        lines.append(f"  class {','.join(leaves)} leaf;")
    return lines
