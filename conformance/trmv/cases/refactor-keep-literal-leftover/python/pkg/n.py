from typing import Any

from pkg.m import Ds


def post(path: str, json: dict[str, Any]) -> None: ...


def bodies() -> None:
    post("/datasets", json={"version": 3, "columns": ["id"]})
    post("/datasets", json={"columns": ["id"]})


def stored() -> Ds:
    return Ds.model_validate({"version": 3, "columns": []})
