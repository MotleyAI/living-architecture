import pkg.a
from typing import overload


@overload
def f(n: int) -> int: ...


@overload
def f(n: str, fallback=pkg.a.f) -> str: ...


def f(n, fallback=None):
    return n


def g():
    return 1
