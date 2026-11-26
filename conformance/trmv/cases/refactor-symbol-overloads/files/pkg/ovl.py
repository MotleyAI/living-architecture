from typing import overload


@overload
def decode(x: int) -> int: ...
@overload
def decode(x: str) -> str: ...
def decode(x: int | str) -> int | str:
    return x


def use() -> int:
    return decode(1)
