"""The canonical element map: every model element, with node mappings from metadata and nested units by convention."""

from __future__ import annotations

from pydantic import BaseModel

from living_architecture.archcheck.index import ArchCheckError
from living_architecture.c4 import RETIRED_ARC42_KEY, Element, ModelParse
from living_architecture.contract import language, message, schema, validate


class MapElement(BaseModel):
    """One model element: a language root (`node` None), a node (`node == id`), or nested under `node`.

    A node's `units` are its declared units in metadata order; `unit` is a nested element's convention unit.
    """

    id: str
    language: str
    node: str | None
    specs: list[str]
    virtual: bool = False
    package: str | None = None
    units: list[str] = []
    unit: str | None = None
    has_elements: bool = False

    @property
    def is_node(self) -> bool:
        return self.node == self.id


class NodeMap(BaseModel):
    elements: list[MapElement]

    def element_ids(self) -> set[str]:
        return {e.id for e in self.elements}

    def language_nodes(self, lang: str) -> list[MapElement]:
        return [e for e in self.elements if e.is_node and e.language == lang]

    def language_derived(self, lang: str) -> list[MapElement]:
        """`lang`'s nested elements that map to a unit, in model order."""
        return [e for e in self.elements if e.unit is not None and e.language == lang]

    def units(self, lang: str) -> list[str]:
        """Every declared, then derived unit of `lang`, in model order, each once."""
        out: list[str] = []
        declared = [u for n in self.language_nodes(lang) for u in n.units]
        for unit in declared + [str(d.unit) for d in self.language_derived(lang)]:
            if unit not in out:
                out.append(unit)
        return out


def separator(lang: str) -> str:
    return language(lang)["unit_separator"]


def _variety(element: Element, roots: set[str]) -> str:
    if element.parent in roots:
        return "virtual" if element.virtual else "precise"
    return "element"


def _metadata_errors(element: Element, roots: set[str]) -> list[str]:
    """The retired-key error first, then the schema errors of the other keys."""
    errors: list[str] = []
    if RETIRED_ARC42_KEY in element.metadata:
        errors.append(message("arch-check.arc42-key-retired", element=element.id))
    rest = {k: v for k, v in element.metadata.items() if k != RETIRED_ARC42_KEY}
    found = validate({**schema("node"), "$ref": f"#/$defs/{_variety(element, roots)}"}, rest)
    return errors + [message("arch-check.metadata-invalid", element=element.id, error=e) for e in found]


def _problems(model: ModelParse, languages: list[str]) -> list[str]:
    problems: list[str] = []
    roots = {e.id for e in model.elements if e.parent is None}
    for element in model.elements:
        if element.parent is None and element.id not in languages:
            problems.append(message("arch-check.root-undeclared", element=element.id))
        elif element.metadata_problems:
            problems += element.metadata_problems
        else:
            problems += _metadata_errors(element, roots)
    problems += [message("arch-check.root-missing", language=lang) for lang in languages if lang not in roots]
    return problems


def _node(element: Element, lang: str) -> MapElement:
    meta = element.metadata
    package = meta.get("package")
    if element.virtual:
        units = list(meta.get("packages", []))
    else:
        units = [str(package), *meta.get("claims", [])]
    return MapElement(
        id=element.id,
        language=lang,
        node=element.id,
        specs=list(meta.get("specs", [])),
        virtual=element.virtual,
        package=package if isinstance(package, str) else None,
        units=units,
    )


def build_node_map(model: ModelParse, languages: list[str]) -> NodeMap:
    """The map for `model`; ArchCheckError naming every root and metadata problem, in model order."""
    problems = _problems(model, languages)
    if problems:
        raise ArchCheckError("; ".join(problems))
    roots = {e.id for e in model.elements if e.parent is None}
    by_id: dict[str, MapElement] = {}
    for element in model.elements:
        specs = list(element.metadata.get("specs", []))
        if element.parent is None:
            by_id[element.id] = MapElement(id=element.id, language=element.id, node=None, specs=specs)
            continue
        if element.parent in roots:
            by_id[element.id] = _node(element, element.parent)
            continue
        lang, local, path = element.id.split(".", 2)
        node = by_id[f"{lang}.{local}"]
        entry = MapElement(id=element.id, language=lang, node=node.id, specs=specs)
        if node.virtual:
            node.has_elements = True
        else:
            sep = separator(lang)
            entry.unit = f"{node.package}{sep}{path.replace('.', sep)}"
        by_id[element.id] = entry
    return NodeMap(elements=list(by_id.values()))


def unit_to_element(node_map: NodeMap, lang: str) -> dict[str, str]:
    """`lang`'s unit -> element FQN: declared units first-wins in model order, then derived units."""
    mapping: dict[str, str] = {}
    for node in node_map.language_nodes(lang):
        for unit in node.units:
            mapping.setdefault(unit, node.id)
    for element in node_map.language_derived(lang):
        mapping.setdefault(str(element.unit), element.id)
    return mapping
