"""B."""
from typing import overload


@overload
def f(n: int) -> int: ...


@overload
def f(n: str, fallback=f) -> str: ...


def f(n, fallback=None):
    return n
