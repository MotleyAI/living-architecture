from typing import Any


def kwonly(*, model_name: str) -> str:
    return model_name


def wrap(**kw: str) -> str:
    return kwonly(**kw)


def pass_on(mapping: dict[str, str]) -> str:
    return kwonly(**mapping)


class Engine:
    def __init__(self, *, models: list[int]) -> None:
        self.size = len(models)


def make(**kw: Any) -> Engine:
    return Engine(**kw)


def calls() -> list[object]:
    return [
        wrap(model_name="x"),
        wrap(**{"model_name": "x"}),
        kwonly(**{"model_name": "x"}),
        pass_on({"model_name": "x"}),
        make(models=[1]),
    ]
