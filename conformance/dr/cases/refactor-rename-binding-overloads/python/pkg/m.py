from typing import overload


@overload
def old(x: int) -> int: ...
@overload
def old(x: str) -> str: ...
def old(x: int | str) -> int | str:
    return x


y = old(1)
