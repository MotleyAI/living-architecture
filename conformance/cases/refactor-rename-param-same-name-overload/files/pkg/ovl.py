from typing import overload


@overload
def f(*, model_name: str) -> str: ...
@overload
def f(*, model_name: int) -> int: ...
def f(*, model_name: str | int) -> str | int:
    return model_name
