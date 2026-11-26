import typing as t
from typing import Any

t = None


def f(Any: int) -> None:
    x: Any = 1


def g() -> t.Any: ...
y: Any
