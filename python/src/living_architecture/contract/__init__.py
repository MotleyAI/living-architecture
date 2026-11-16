"""The shared contract, loaded from the vendored snapshot."""

from living_architecture.contract.glob import glob_match
from living_architecture.contract.os_error import (
    display_path,
    is_regular_file,
    os_error_reason,
    os_error_text,
)
from living_architecture.contract.regex import is_portable_regex
from living_architecture.contract.render import canonical_repr, message, normalize, render_template
from living_architecture.contract.schema import materialize_defaults, validate
from living_architecture.contract.snapshot import (
    architecture,
    base_fetch_timeout,
    check_ids,
    compute_hash,
    config_file,
    config_formats,
    contract_hash,
    conventions,
    findings,
    is_test_file,
    language,
    language_ids,
    language_of,
    literal_value_forbidden,
    local_config_file,
    manifest,
    schema,
    script_path,
    snapshot_dir,
    timing_phases,
)
from living_architecture.contract.yaml_profile import DuplicateKeyError, YAMLError, load_yaml

__all__ = [
    "DuplicateKeyError",
    "YAMLError",
    "architecture",
    "base_fetch_timeout",
    "canonical_repr",
    "check_ids",
    "compute_hash",
    "config_file",
    "config_formats",
    "contract_hash",
    "conventions",
    "display_path",
    "findings",
    "glob_match",
    "is_portable_regex",
    "is_regular_file",
    "is_test_file",
    "language",
    "language_ids",
    "language_of",
    "literal_value_forbidden",
    "load_yaml",
    "local_config_file",
    "manifest",
    "materialize_defaults",
    "message",
    "normalize",
    "os_error_reason",
    "os_error_text",
    "render_template",
    "schema",
    "script_path",
    "snapshot_dir",
    "timing_phases",
    "validate",
]
