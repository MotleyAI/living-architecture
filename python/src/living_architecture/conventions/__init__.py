"""The conventions gate and the comment counter for every language; facts come from `lang` or the other twin."""

from living_architecture.conventions.comments import count_comments
from living_architecture.conventions.facts import emit, language_of
from living_architecture.conventions.gate import (
    FileCounts,
    Violation,
    changed_source_files,
    check_conventions,
    check_file,
    files_label,
    is_test_file,
    resolve_base_ref,
    waived,
)

__all__ = [
    "FileCounts",
    "Violation",
    "changed_source_files",
    "check_conventions",
    "check_file",
    "count_comments",
    "emit",
    "files_label",
    "is_test_file",
    "language_of",
    "resolve_base_ref",
    "waived",
]
