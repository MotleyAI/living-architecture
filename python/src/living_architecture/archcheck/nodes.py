"""The canonical node/unit map: one root per language, nodes from model metadata, nested elements by convention."""

from __future__ import annotations

from pydantic import BaseModel

from living_architecture.archcheck.index import ArchCheckError
from living_architecture.c4 import Element, ModelParse
from living_architecture.contract import language, message, schema, validate


class Node(BaseModel):
    """A child of a language root; `units` are its declared units in metadata order."""

    id: str
    language: str
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
    language: str
    unit: str


class NodeMap(BaseModel):
    nodes: list[Node]
    derived: list[Derived]

    def node_ids(self) -> set[str]:
        return {n.id for n in self.nodes}

    def language_nodes(self, lang: str) -> list[Node]:
        return [n for n in self.nodes if n.language == lang]

    def language_derived(self, lang: str) -> list[Derived]:
        return [d for d in self.derived if d.language == lang]

    def units(self, lang: str) -> list[str]:
        """Every declared, then derived unit of `lang`, in model order, each once."""
        out: list[str] = []
        for unit in [u for n in self.language_nodes(lang) for u in n.units] + [d.unit for d in self.language_derived(lang)]:
            if unit not in out:
                out.append(unit)
        return out


def separator(lang: str) -> str:
    return language(lang)["unit_separator"]


def _metadata_errors(element: Element) -> list[str]:
    variety = "virtual" if element.virtual else "precise"
    errors = validate({**schema("node"), "$ref": f"#/$defs/{variety}"}, element.metadata)
    return [message("arch-check.metadata-invalid", element=element.id, error=e) for e in errors]


def _node(element: Element, lang: str) -> Node:
    meta = element.metadata
    package = meta.get("package")
    if element.virtual:
        units = list(meta.get("packages", []))
    else:
        units = [str(package), *meta.get("claims", [])]
    arc42 = meta.get("arc42")
    return Node(
        id=element.id,
        language=lang,
        virtual=element.virtual,
        package=package if isinstance(package, str) else None,
        units=units,
        arc42=arc42 if isinstance(arc42, str) else None,
        specs=list(meta.get("specs", [])),
    )


def _problems(model: ModelParse, languages: list[str]) -> list[str]:
    problems: list[str] = []
    roots = {e.id for e in model.elements if e.parent is None}
    for element in model.elements:
        if element.parent is None:
            if element.id not in languages:
                problems.append(message("arch-check.root-undeclared", element=element.id))
            elif element.has_metadata or element.metadata_problems:
                problems.append(message("arch-check.metadata-on-root", element=element.id))
        elif element.metadata_problems:
            problems += element.metadata_problems
        elif element.parent not in roots:
            if element.has_metadata:
                problems.append(message("arch-check.metadata-on-nested", element=element.id))
        else:
            problems += _metadata_errors(element)
    problems += [message("arch-check.root-missing", language=lang) for lang in languages if lang not in roots]
    return problems


def build_node_map(model: ModelParse, languages: list[str]) -> NodeMap:
    """The map for `model`; ArchCheckError naming every root and metadata problem, in model order."""
    problems = _problems(model, languages)
    if problems:
        raise ArchCheckError("; ".join(problems))
    roots = {e.id for e in model.elements if e.parent is None}
    nodes = {e.id: _node(e, e.parent) for e in model.elements if e.parent in roots}
    derived: list[Derived] = []
    for element in model.elements:
        if element.parent is None or element.parent in roots:
            continue
        lang, local, path = element.id.split(".", 2)
        node = nodes[f"{lang}.{local}"]
        if node.virtual:
            node.has_elements = True
        else:
            sep = separator(lang)
            derived.append(
                Derived(id=element.id, node=node.id, language=lang, unit=f"{node.package}{sep}{path.replace('.', sep)}")
            )
    return NodeMap(nodes=list(nodes.values()), derived=derived)


def unit_to_element(node_map: NodeMap, lang: str) -> dict[str, str]:
    """`lang`'s unit -> element FQN: declared units first-wins in model order, then derived units."""
    mapping: dict[str, str] = {}
    for node in node_map.language_nodes(lang):
        for unit in node.units:
            mapping.setdefault(unit, node.id)
    for element in node_map.language_derived(lang):
        mapping.setdefault(element.unit, element.id)
    return mapping
