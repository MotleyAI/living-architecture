"""The canonical node/unit map: nodes from model metadata, nested elements mapped by convention."""

from __future__ import annotations

from pydantic import BaseModel

from living_architecture.archcheck.index import ArchCheckError
from living_architecture.c4 import Element, ModelParse
from living_architecture.contract import message, schema, validate


class Node(BaseModel):
    """A top-level model element; `units` are its declared units in metadata order."""

    id: str
    virtual: bool
    package: str | None
    units: list[str]
    arc42: str | None
    specs: list[str]
    has_elements: bool = False


class Derived(BaseModel):
    """An element nested under a precise node and the unit it maps to by convention."""

    id: str
    node: str
    unit: str


class NodeMap(BaseModel):
    nodes: list[Node]
    derived: list[Derived]

    def node_ids(self) -> set[str]:
        return {n.id for n in self.nodes}


def _metadata_errors(element: Element) -> list[str]:
    variety = "virtual" if element.virtual else "precise"
    errors = validate({**schema("node"), "$ref": f"#/$defs/{variety}"}, element.metadata)
    return [message("arch-check.metadata-invalid", element=element.id, error=e) for e in errors]


def _node(element: Element) -> Node:
    meta = element.metadata
    package = meta.get("package")
    if element.virtual:
        units = list(meta.get("packages", []))
    else:
        units = [str(package), *meta.get("claims", [])]
    arc42 = meta.get("arc42")
    return Node(
        id=element.id,
        virtual=element.virtual,
        package=package if isinstance(package, str) else None,
        units=units,
        arc42=arc42 if isinstance(arc42, str) else None,
        specs=list(meta.get("specs", [])),
    )


def build_node_map(model: ModelParse) -> NodeMap:
    """The map for `model`; ArchCheckError naming every metadata problem, in model order."""
    problems: list[str] = []
    for element in model.elements:
        if element.metadata_problems:
            problems += element.metadata_problems
        elif element.parent is not None:
            if element.metadata:
                problems.append(message("arch-check.metadata-on-nested", element=element.id))
        else:
            problems += _metadata_errors(element)
    if problems:
        raise ArchCheckError("; ".join(problems))
    nodes = {e.id: _node(e) for e in model.elements if e.parent is None}
    derived: list[Derived] = []
    for element in model.elements:
        if element.parent is None:
            continue
        node_id, _, path = element.id.partition(".")
        node = nodes[node_id]
        if node.virtual:
            node.has_elements = True
        else:
            derived.append(Derived(id=element.id, node=node_id, unit=f"{node.package}.{path}"))
    return NodeMap(nodes=list(nodes.values()), derived=derived)


def unit_to_element(node_map: NodeMap) -> dict[str, str]:
    """Unit -> element FQN: declared units first-wins in model order, then derived units."""
    mapping: dict[str, str] = {}
    for node in node_map.nodes:
        for unit in node.units:
            mapping.setdefault(unit, node.id)
    for element in node_map.derived:
        mapping.setdefault(element.unit, element.id)
    return mapping
