"""la's shared contract, loaded from its vendored snapshot; an id la's registry lacks renders from dr's."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from deterministic_refactor.contract import Snapshot, render_template
from deterministic_refactor.contract import contract_hash as dr_contract_hash
from deterministic_refactor.contract import materialize_defaults as dr_materialize_defaults
from deterministic_refactor.contract import message as dr_message
from deterministic_refactor.contract import validate as dr_validate
from deterministic_refactor.twin import Identity
from living_architecture import __version__

LA = Snapshot(Path(__file__).resolve().parent / "data")


def snapshot_dir() -> Path:
    return LA.root


def contract_hash() -> str:
    """The hash recorded when la's snapshot was vendored."""
    return LA.contract_hash()


def schema(name: str) -> dict[str, Any]:
    return LA.schema(name)


def findings() -> dict[str, str]:
    return LA.findings()


def check_ids() -> frozenset[str]:
    return frozenset(LA.yaml("findings.yaml")["check_ids"])


def manifest() -> dict[str, Any]:
    return LA.manifest()


def conventions() -> dict[str, Any]:
    return LA.yaml("conventions.yaml")


def architecture() -> dict[str, Any]:
    return LA.yaml("architecture.yaml")


def config_file() -> str:
    """la's committed config file, relative to the repo root."""
    return LA.yaml("config.yaml")["file"]


def local_config_file() -> str:
    """One contributor's git-ignored overrides of it."""
    return LA.yaml("config.yaml")["local_file"]


def script_path(name: str) -> Path:
    return LA.script_path(name)


def message(template_id: str, **values: object) -> str:
    """The finding `template_id` rendered from la's registry, else from dr's."""
    template = findings().get(template_id)
    return dr_message(template_id, **values) if template is None else render_template(template, values)


def validate(schema: dict[str, Any], data: Any) -> list[str]:
    """`data` against an la schema, whose `$ref`s into dr's schemas resolve."""
    return dr_validate(schema, data, (LA,))


def materialize_defaults(schema: dict[str, Any], data: object) -> Any:
    """`data` with an la schema's defaults filled in, following its `$ref`s into dr's schemas."""
    return dr_materialize_defaults(schema, data, (LA,))


def identity() -> Identity:
    """la's twin identity: its doctor, version, la's contract hash and the dr hash of the dr library it runs with."""
    cli = LA.yaml("cli.yaml")
    hashes = (contract_hash(), dr_contract_hash())
    return Identity(package=cli["package"], doctor=cli["doctor"], version=__version__, hashes=hashes, contract=LA)
