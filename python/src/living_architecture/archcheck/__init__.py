"""Living-architecture cross-walk checker: code, LikeC4 model, arc42 docs and specs agree."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from living_architecture import twin
from living_architecture.archcheck.claims import check_claims
from living_architecture.archcheck.docs import check_arc42, check_legacy_ratchet, check_spec_mapping
from living_architecture.archcheck.facts import Facts, native_facts, native_top_level_facts
from living_architecture.archcheck.index import (
    ArchCheckError,
    Layout,
    declared_languages,
    load_index,
    resolve_layout,
)
from living_architecture.archcheck.nodes import NodeMap, build_node_map, unit_to_element
from living_architecture.archcheck.scaffold import run_scaffold
from living_architecture.archcheck.tags import check_enforced_tags
from living_architecture.archcheck.truth import check_model_truth, license, measure_runtime_edges
from living_architecture.c4 import ModelParse, check_diagrams_fresh, parse_model, parse_views
from living_architecture.config import ConfigError, load_config
from living_architecture.contract import message

__all__ = [
    "ArchCheckError",
    "Facts",
    "Layout",
    "NodeMap",
    "build_node_map",
    "license",
    "measure_runtime_edges",
    "resolve_layout",
    "run",
    "run_checks",
    "run_scaffold",
    "unit_to_element",
]


class _Setup(BaseModel):
    """What every check reads: the index, its languages, the model and the node map."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    index: dict[str, Any]
    languages: list[str]
    model: ModelParse
    node_map: NodeMap


def _setup(root: Path) -> _Setup:
    index = load_index(root)
    languages = declared_languages(index)
    model = parse_model(root)
    return _Setup(index=index, languages=languages, model=model, node_map=build_node_map(model, languages))


def _facts(root: Path, setup: _Setup, language: str) -> Facts:
    """Native facts in-process; another language's from its twin."""
    if language == twin.NATIVE_LANGUAGE:
        return native_facts(resolve_layout(root, setup.index[language]), setup.node_map, language)
    return Facts.model_validate(twin.request_facts(language, root, setup.node_map.units(language)))


def _findings(root: Path) -> list[str]:
    setup = _setup(root)
    facts = [_facts(root, setup, language) for language in setup.languages]
    model = setup.model
    views = parse_views(root=root, model=model)
    witnesses: dict[tuple[str, str], tuple[str, str]] = {}
    for language_facts in facts:
        for edge in language_facts.edges:
            witnesses.setdefault((edge.src, edge.dst), (edge.src_module, edge.dst_module))
    arrows = [(r.src, r.dst) for r in model.relations]
    legacy_count = sum(1 for r in model.relations if r.legacy)
    findings: list[str] = []
    for language_facts in facts:
        findings += check_claims(setup.node_map, language_facts)
    findings += check_arc42(root, setup.index, setup.node_map)
    findings += check_spec_mapping(root, setup.index, setup.node_map)
    findings += check_legacy_ratchet(setup.index, legacy_count)
    findings += check_model_truth(witnesses, arrows)
    findings += check_enforced_tags(root, load_config(root).issue_key_re(), setup.languages)
    findings += check_diagrams_fresh(root=root, model=model, views=views)
    return findings


def run_checks(root: Path) -> list[str]:
    """Every finding for the repo at `root`; ArchCheckError when the setup is too broken to check."""
    try:
        return _findings(root)
    except OSError as exc:
        raise ArchCheckError(str(exc)) from exc


def _emit(root: Path, language: str, *, top_level: bool) -> Facts:
    if top_level:
        index = load_index(root)
        if language not in declared_languages(index):
            raise ArchCheckError(message("arch-check.no-language-section"))
        return native_top_level_facts(resolve_layout(root, index[language]), language)
    setup = _setup(root)
    if language not in setup.languages:
        raise ArchCheckError(message("arch-check.no-language-section"))
    return _facts(root, setup, language)


def emit_facts(root: Path, language: str, *, top_level: bool = False) -> dict[str, Any]:
    """The native language's facts document (`top_level`: edges between top-level units, no model)."""
    if language != twin.NATIVE_LANGUAGE:
        raise ArchCheckError(message("twin.not-native", language=language))
    try:
        return _emit(root, language, top_level=top_level).document()
    except OSError as exc:
        raise ArchCheckError(str(exc)) from exc


def _setup_error(error: str) -> int:
    print(message("arch-check.setup-error", error=error), file=sys.stderr)
    return 2


def run(root: Path, *, language: str | None = None, emit: str | None = None, top_level: bool = False) -> int:
    """`la-arch-check`: print the findings and a summary, or (`--emit facts`) one language's facts."""
    try:
        if emit == "facts" and language is not None:
            print(json.dumps(emit_facts(root, language, top_level=top_level), indent=2))
            return 0
        findings = run_checks(root)
    except (ArchCheckError, ConfigError, twin.TwinError) as exc:
        return _setup_error(str(exc))
    except twin.RelayedFailure:
        return 2
    for finding in findings:
        print(finding)
    if findings:
        print(message("arch-check.summary", count=len(findings)))
        return 1
    print(message("arch-check.ok"))
    return 0
