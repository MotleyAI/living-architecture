"""The LikeC4 model: the single parser of the constrained `.c4` convention, views, and mermaid diagrams."""

from living_architecture.c4.diagrams import DiagramsError, check_diagrams_fresh, diagram_block, generate, run
from living_architecture.c4.index import read_index
from living_architecture.c4.layout import layout_problem, model_file, sources, views_file
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
    "DEFAULT_VIEW_DEPTH",
    "DiagramsError",
    "Edge",
    "Element",
    "ModelParse",
    "Relation",
    "View",
    "ViewsParse",
    "check_diagrams_fresh",
    "diagram_block",
    "generate",
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
