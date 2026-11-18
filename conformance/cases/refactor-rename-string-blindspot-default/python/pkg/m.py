from typing import Any


class Ds:
    def __init__(self) -> None:
        self.columns: list[str] = []


def a(x: Any) -> object:
    return x.columns


def b(x: Any) -> object:
    return getattr(x, "columns", None)
