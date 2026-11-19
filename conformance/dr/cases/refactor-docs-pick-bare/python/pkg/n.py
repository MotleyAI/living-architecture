from typing import Any


def post(path: str, json: dict[str, Any]) -> None: ...


def rest_body() -> None:
    post("/datasets", json={"name": "orders", "columns": ["id"]})
    post("/views", json={"columns": ["id"]})
