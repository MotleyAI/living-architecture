"""la's shared contract, loaded from its vendored snapshot; an id la's registry lacks renders from trmv's."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from living_architecture import __version__
from trmv.contract import Snapshot, render_template
from trmv.contract import contract_hash as trmv_contract_hash
from trmv.contract import materialize_defaults as trmv_materialize_defaults
from trmv.contract import message as trmv_message
from trmv.contract import validate as trmv_validate
from trmv.twin import Identity

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


def stealth_path(key: str) -> str:
    """A stealth-mode path in la's stealth directory: `plans_dir`, `waiver_ledger` or `openspec_store`."""
    return LA.yaml("config.yaml")[key]


def stealth_registry() -> tuple[list[str], str]:
    """la's stealth path registry, and the prefix whose paths count when the repo tracks none under it."""
    config = LA.yaml("config.yaml")
    return list(config["stealth_registry"]), config["stealth_registry_prefix"]


def leak_token_groups() -> tuple[list[str], list[str]]:
    """The core and the waivable leak tokens of the list."""
    tokens = LA.yaml("vectors/stealth-leaks.yaml")
    return list(tokens["core"]), list(tokens["waivable"])


def script_path(name: str) -> Path:
    return LA.script_path(name)


def message(template_id: str, **values: object) -> str:
    """The finding `template_id` rendered from la's registry, else from trmv's."""
    template = findings().get(template_id)
    return trmv_message(template_id, **values) if template is None else render_template(template, values)


def validate(schema: dict[str, Any], data: Any) -> list[str]:
    """`data` against an la schema, whose `$ref`s into trmv's schemas resolve."""
    return trmv_validate(schema, data, (LA,))


def materialize_defaults(schema: dict[str, Any], data: object) -> Any:
    """`data` with an la schema's defaults filled in, following its `$ref`s into trmv's schemas."""
    return trmv_materialize_defaults(schema, data, (LA,))


def identity() -> Identity:
    """la's twin identity: its doctor, version, la's contract hash and the trmv hash of the trmv library it runs with."""
    cli = LA.yaml("cli.yaml")
    hashes = (contract_hash(), trmv_contract_hash())
    return Identity(package=cli["package"], doctor=cli["doctor"], version=__version__, hashes=hashes, contract=LA)
