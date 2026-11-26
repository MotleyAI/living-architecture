"""Schema validation and default materialization, across trmv's schemas and any other contract's."""

from __future__ import annotations

import copy
from functools import cache
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing._core import Resolver
from referencing.jsonschema import DRAFT202012

from trmv.contract.snapshot import TRMV, Snapshot


@cache
def _store(snapshots: tuple[Snapshot, ...]) -> Registry[Any]:
    """Every schema of `snapshots` under its `$id`, so cross-file `$ref`s resolve."""
    resources = [
        Resource.from_contents(snapshot.schema(name), default_specification=DRAFT202012)
        for snapshot in snapshots
        for name in snapshot.schema_names()
    ]
    return Registry().with_resources((resource.id() or "", resource) for resource in resources)


@cache
def _shared_validator(snapshots: tuple[Snapshot, ...], schema_id: str) -> Draft202012Validator:
    return Draft202012Validator(_store(snapshots)[schema_id].contents, registry=_store(snapshots))


def _validator(schema: dict[str, Any], snapshots: tuple[Snapshot, ...]) -> Draft202012Validator:
    """A shared schema's validator by its `$id`; any other schema built afresh against the store."""
    schema_id = schema.get("$id")
    store = _store(snapshots)
    if isinstance(schema_id, str) and (shared := store.get(schema_id)) is not None and shared.contents is schema:
        return _shared_validator(snapshots, schema_id)
    return Draft202012Validator(schema, registry=store)


def validate(schema: dict[str, Any], data: Any, extra: tuple[Snapshot, ...] = ()) -> list[str]:
    """Sorted `key.path: message` lines, one per violation; empty when valid. `extra`: other contracts' schemas."""
    errors = []
    for error in _validator(schema, (TRMV, *extra)).iter_errors(data):
        path = ".".join(str(part) for part in error.absolute_path)
        errors.append(f"{path}: {error.message}" if path else error.message)
    return sorted(errors)


def _deref(schema: dict[str, Any], resolver: Resolver[Any]) -> tuple[dict[str, Any], Resolver[Any]]:
    """`schema` with its `$ref`s followed, and the resolver for what it refers to."""
    while "$ref" in schema:
        resolved = resolver.lookup(schema["$ref"])
        schema, resolver = resolved.contents, resolved.resolver
    return schema, resolver


def _has_defaults(schema: dict[str, Any], resolver: Resolver[Any]) -> bool:
    for sub in schema.get("properties", {}).values():
        sub, sub_resolver = _deref(sub, resolver)
        if "default" in sub or _has_defaults(sub, sub_resolver):
            return True
    return False


def _fill(schema: dict[str, Any], value: object, resolver: Resolver[Any]) -> object:
    if not isinstance(value, dict):
        return value
    out = dict(value)
    for key, sub in schema.get("properties", {}).items():
        sub, sub_resolver = _deref(sub, resolver)
        if key in out:
            out[key] = _fill(sub, out[key], sub_resolver)
        elif "default" in sub:
            out[key] = copy.deepcopy(sub["default"])
        elif _has_defaults(sub, sub_resolver):
            out[key] = _fill(sub, {}, sub_resolver)
    return out


def materialize_defaults(schema: dict[str, Any], data: object, extra: tuple[Snapshot, ...] = ()) -> Any:
    """`data` (None = missing document) with schema defaults filled in, following `$ref`s as inline definitions;
    explicit values are kept. `extra`: other contracts' schemas."""
    resolver = _store((TRMV, *extra)).resolver(base_uri=str(schema.get("$id", "")))
    schema, resolver = _deref(schema, resolver)
    return _fill(schema, {} if data is None else data, resolver)
