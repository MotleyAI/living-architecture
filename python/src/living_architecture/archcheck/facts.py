"""One language's architecture facts: unit statuses, top-level units and witnessed element edges."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from living_architecture import __version__
from living_architecture.archcheck.index import Layout
from living_architecture.archcheck.nodes import NodeMap, unit_to_element
from living_architecture.archcheck.truth import measure_runtime_edges
from living_architecture.contract import contract_hash
from living_architecture.lang import top_level_units, unit_exists


class UnitFact(BaseModel):
    unit: str
    status: str
    candidates: list[str] = []


class EdgeFact(BaseModel):
    src: str
    dst: str
    src_module: str
    dst_module: str


class Facts(BaseModel):
    language: str
    version: str
    contract_hash: str
    units: list[UnitFact]
    top_level_units: list[str]
    edges: list[EdgeFact]

    def unit(self, unit: str) -> UnitFact:
        return next(u for u in self.units if u.unit == unit)

    def document(self) -> dict[str, Any]:
        """The facts schema's JSON shape (candidates only on ambiguous units)."""
        doc = self.model_dump()
        for unit in doc["units"]:
            if unit["status"] != "ambiguous":
                del unit["candidates"]
        return doc


def _facts(layout: Layout, language: str, units: list[UnitFact], attribution: dict[str, str]) -> Facts:
    witnesses = measure_runtime_edges(layout, attribution)
    return Facts(
        language=language,
        version=__version__,
        contract_hash=contract_hash(),
        units=units,
        top_level_units=sorted(top_level_units(layout.source_root, layout.root_package)),
        edges=[
            EdgeFact(src=src, dst=dst, src_module=src_module, dst_module=dst_module)
            for (src, dst), (src_module, dst_module) in sorted(witnesses.items())
        ],
    )


def native_facts(layout: Layout, node_map: NodeMap, language: str) -> Facts:
    """The Python facts, measured in-process."""
    units = [
        UnitFact(unit=unit, status="present" if unit_exists(layout.source_root, unit) else "missing")
        for unit in node_map.units(language)
    ]
    return _facts(layout, language, units, unit_to_element(node_map, language))


def native_top_level_facts(layout: Layout, language: str) -> Facts:
    """The Python facts with edges between top-level units; no model involved."""
    tops = top_level_units(layout.source_root, layout.root_package)
    return _facts(layout, language, [], {unit: unit for unit in tops})
