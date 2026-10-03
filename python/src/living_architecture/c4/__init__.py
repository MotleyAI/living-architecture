"""The LikeC4 model: the single parser of the constrained `.c4` convention, views, and mermaid diagrams."""

from living_architecture.c4.diagrams import DiagramsError, check_diagrams_fresh, generate, run
from living_architecture.c4.mermaid import render_mermaid
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
    "generate",
    "is_or_ancestor",
    "parse_model",
    "parse_views",
    "project",
    "render_mermaid",
    "roots",
    "run",
]
