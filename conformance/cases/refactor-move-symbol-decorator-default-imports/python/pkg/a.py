import functools
from os import sep


@functools.cache
def f(s: str = sep) -> str:
    return s


def g() -> int:
    return 2
