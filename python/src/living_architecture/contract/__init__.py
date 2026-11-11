"""The shared contract, loaded from the vendored snapshot."""

from living_architecture.contract.glob import glob_match
from living_architecture.contract.regex import is_portable_regex
from living_architecture.contract.render import canonical_repr, message, normalize, render_template
from living_architecture.contract.schema import materialize_defaults, validate
from living_architecture.contract.snapshot import (
    architecture,
    base_fetch_timeout,
    check_ids,
    compute_hash,
    config_file,
    config_format,
    contract_hash,
    conventions,
    findings,
    is_test_file,
    language,
    language_ids,
    language_of,
    local_config_file,
    manifest,
    schema,
    script_path,
    snapshot_dir,
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
    "config_format",
    "contract_hash",
    "conventions",
    "findings",
    "glob_match",
    "is_portable_regex",
    "is_test_file",
    "language",
    "language_ids",
    "language_of",
    "load_yaml",
    "local_config_file",
    "manifest",
    "materialize_defaults",
    "message",
    "normalize",
    "render_template",
    "schema",
    "script_path",
    "snapshot_dir",
    "validate",
]
