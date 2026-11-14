from typing import overload as ov


@ov
def f(*, model_name: str) -> str: ...
@ov
def f(*, model_name: int) -> int: ...
def f(*, model_name: str | int) -> str | int:
    return model_name


x = f(model_name="x")
