"""Schema validation and default materialization."""

from __future__ import annotations

import copy
from functools import cache
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from living_architecture.contract.snapshot import schema, schema_names


@cache
def _store() -> Registry[Any]:
    """Every shared schema under its `$id`, so cross-file `$ref`s resolve."""
    resources = [Resource.from_contents(schema(name), default_specification=DRAFT202012) for name in schema_names()]
    return Registry().with_resources((resource.id() or "", resource) for resource in resources)


@cache
def _shared_validator(schema_id: str) -> Draft202012Validator:
    return Draft202012Validator(_store()[schema_id].contents, registry=_store())


def _validator(schema: dict[str, Any]) -> Draft202012Validator:
    """A shared schema's validator by its `$id`; any other schema built afresh against the store."""
    schema_id = schema.get("$id")
    if isinstance(schema_id, str) and (shared := _store().get(schema_id)) is not None and shared.contents is schema:
        return _shared_validator(schema_id)
    return Draft202012Validator(schema, registry=_store())


def validate(schema: dict[str, Any], data: Any) -> list[str]:
    """Sorted `key.path: message` lines, one per violation; empty when valid."""
    errors = []
    for error in _validator(schema).iter_errors(data):
        path = ".".join(str(part) for part in error.absolute_path)
        errors.append(f"{path}: {error.message}" if path else error.message)
    return sorted(errors)


def _has_defaults(schema: dict[str, Any]) -> bool:
    return any("default" in sub or _has_defaults(sub) for sub in schema.get("properties", {}).values())


def _fill(schema: dict[str, Any], value: object) -> object:
    if not isinstance(value, dict):
        return value
    out = dict(value)
    for key, sub in schema.get("properties", {}).items():
        if key in out:
            out[key] = _fill(sub, out[key])
        elif "default" in sub:
            out[key] = copy.deepcopy(sub["default"])
        elif _has_defaults(sub):
            out[key] = _fill(sub, {})
    return out


def materialize_defaults(schema: dict[str, Any], data: object) -> Any:
    """`data` (None = missing document) with schema defaults filled in; explicit values are kept."""
    return _fill(schema, {} if data is None else data)
