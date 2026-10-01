"""The shared contract, loaded from the vendored snapshot."""

from living_architecture.contract.glob import glob_match
from living_architecture.contract.regex import is_portable_regex
from living_architecture.contract.render import canonical_repr, message, normalize, render_template
from living_architecture.contract.schema import materialize_defaults, validate
from living_architecture.contract.snapshot import (
    check_ids,
    compute_hash,
    contract_hash,
    conventions,
    findings,
    language,
    manifest,
    schema,
    script_path,
    snapshot_dir,
)
from living_architecture.contract.yaml_profile import YAMLError, load_yaml

__all__ = [
    "YAMLError",
    "canonical_repr",
    "check_ids",
    "compute_hash",
    "contract_hash",
    "conventions",
    "findings",
    "glob_match",
    "is_portable_regex",
    "language",
    "load_yaml",
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
