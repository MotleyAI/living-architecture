from typing import overload


@overload
def f(x: int) -> int: ...


@overload
def f(x: str) -> str: ...


def f(x: int | str) -> int | str:
    return x


def g() -> int:
    return 1
