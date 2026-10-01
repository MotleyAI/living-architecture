"""The conventions gate and the comment counter; language detectors come from `lang`."""

from living_architecture.conventions.comments import count_comments
from living_architecture.conventions.gate import (
    FileCounts,
    Violation,
    changed_source_files,
    check_conventions,
    check_file,
    is_test_file,
    resolve_base_ref,
    run,
)

__all__ = [
    "FileCounts",
    "Violation",
    "changed_source_files",
    "check_conventions",
    "check_file",
    "count_comments",
    "is_test_file",
    "resolve_base_ref",
    "run",
]
