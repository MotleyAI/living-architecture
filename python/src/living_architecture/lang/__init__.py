"""The Python language adapter (`ast`/`tokenize`): units, import targets, rule detectors, line sets."""

from living_architecture.lang.source import (
    Detection,
    ParseFailure,
    SourceAnalysis,
    analyze,
    comment_doc_counts,
)
from living_architecture.lang.units import (
    SourceModule,
    import_targets,
    source_modules,
    top_level_units,
    unit_exists,
)

__all__ = [
    "Detection",
    "ParseFailure",
    "SourceAnalysis",
    "SourceModule",
    "analyze",
    "comment_doc_counts",
    "import_targets",
    "source_modules",
    "top_level_units",
    "unit_exists",
]
