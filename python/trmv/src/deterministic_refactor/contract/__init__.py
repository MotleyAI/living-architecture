"""dr's shared contract, loaded from its vendored snapshot; `Snapshot` loads another package's."""

from deterministic_refactor.contract.glob import glob_match
from deterministic_refactor.contract.os_error import (
    display_path,
    is_regular_file,
    os_error_reason,
    os_error_text,
)
from deterministic_refactor.contract.plugin import plugin_problem
from deterministic_refactor.contract.regex import capturing_groups, is_portable_regex
from deterministic_refactor.contract.render import canonical_repr, message, normalize, render_template
from deterministic_refactor.contract.schema import materialize_defaults, validate
from deterministic_refactor.contract.snapshot import (
    DR,
    Snapshot,
    base_fetch_timeout,
    compute_hash,
    config_files,
    config_formats,
    contract_hash,
    findings,
    is_test_file,
    language,
    language_ids,
    language_keys,
    language_of,
    literal_value_forbidden,
    manifest,
    schema,
    schema_names,
    snapshot_dir,
    timing_phases,
)
from deterministic_refactor.contract.yaml_profile import DuplicateKeyError, YAMLError, load_yaml

__all__ = [
    "DR",
    "DuplicateKeyError",
    "Snapshot",
    "YAMLError",
    "base_fetch_timeout",
    "canonical_repr",
    "capturing_groups",
    "compute_hash",
    "config_files",
    "config_formats",
    "contract_hash",
    "display_path",
    "findings",
    "glob_match",
    "is_portable_regex",
    "is_regular_file",
    "is_test_file",
    "language",
    "language_ids",
    "language_keys",
    "language_of",
    "literal_value_forbidden",
    "load_yaml",
    "manifest",
    "materialize_defaults",
    "message",
    "normalize",
    "os_error_reason",
    "os_error_text",
    "plugin_problem",
    "render_template",
    "schema",
    "schema_names",
    "snapshot_dir",
    "timing_phases",
    "validate",
]
