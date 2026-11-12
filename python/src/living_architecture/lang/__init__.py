"""The Python language adapter: units, import targets, dependency edges, conventions facts, the basedpyright specifics."""

from living_architecture.lang.edges import dependency_edges
from living_architecture.lang.source import (
    Detection,
    ParseFailure,
    SourceAnalysis,
    analyze,
    comment_doc_counts,
    conventions_facts,
)
from living_architecture.lang.typecheck import (
    BASEDPYRIGHT_WRITE_FLAG,
    PYRIGHT_PATCH_PRELOAD,
    PyrightPatch,
    basedpyright_exit,
    empty_basedpyright_baseline,
    pyright_patch_env,
    read_pyright_patch,
)
from living_architecture.lang.units import (
    SourceModule,
    import_targets,
    source_modules,
    top_level_units,
    unit_exists,
)

__all__ = [
    "BASEDPYRIGHT_WRITE_FLAG",
    "PYRIGHT_PATCH_PRELOAD",
    "Detection",
    "ParseFailure",
    "PyrightPatch",
    "SourceAnalysis",
    "SourceModule",
    "analyze",
    "basedpyright_exit",
    "comment_doc_counts",
    "conventions_facts",
    "dependency_edges",
    "empty_basedpyright_baseline",
    "import_targets",
    "pyright_patch_env",
    "read_pyright_patch",
    "source_modules",
    "top_level_units",
    "unit_exists",
]
