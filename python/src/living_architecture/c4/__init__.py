"""The LikeC4 model: the single parser of the constrained `.c4` convention, views, and mermaid diagrams."""

from living_architecture.c4.diagrams import DiagramsError, check_diagrams_fresh, diagram_block, generate, run
from living_architecture.c4.index import read_index
from living_architecture.c4.layout import (
    ARCH_DIR,
    DOC_SUFFIX,
    RETIRED_ARC42_KEY,
    architecture_files,
    element_doc,
    is_flat_doc,
    layout_problem,
    model_file,
    sources,
    views_file,
)
from living_architecture.c4.mermaid import render_mermaid
from living_architecture.c4.migrate import run as run_migrate
from living_architecture.c4.model import (
    Element,
    ModelParse,
    Relation,
    is_or_ancestor,
    parse_model,
    project,
    roots,
)
from living_architecture.c4.views import DEFAULT_VIEW_DEPTH, Edge, View, ViewsParse, parse_views

__all__ = [
    "ARCH_DIR",
    "DEFAULT_VIEW_DEPTH",
    "DOC_SUFFIX",
    "RETIRED_ARC42_KEY",
    "DiagramsError",
    "Edge",
    "Element",
    "ModelParse",
    "Relation",
    "View",
    "ViewsParse",
    "architecture_files",
    "check_diagrams_fresh",
    "diagram_block",
    "element_doc",
    "generate",
    "is_flat_doc",
    "is_or_ancestor",
    "layout_problem",
    "model_file",
    "parse_model",
    "parse_views",
    "project",
    "read_index",
    "render_mermaid",
    "roots",
    "run",
    "run_migrate",
    "sources",
    "views_file",
]
