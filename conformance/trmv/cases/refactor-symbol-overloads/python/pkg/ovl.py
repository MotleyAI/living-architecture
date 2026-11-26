from typing import overload


@overload
def parse(x: int) -> int: ...
@overload
def parse(x: str) -> str: ...
def parse(x: int | str) -> int | str:
    return x


def use() -> int:
    return parse(1)
