from collections.abc import Callable
from typing import TypeVar

F = TypeVar("F")


def field_validator(*names: str) -> Callable[[F], F]:
    def wrap(f: F) -> F:
        return f

    return wrap


class Look:
    def __init__(self) -> None:
        self.columns: list[str] = []

    @field_validator("columns")
    def check(self) -> list[str]:
        return self.columns
