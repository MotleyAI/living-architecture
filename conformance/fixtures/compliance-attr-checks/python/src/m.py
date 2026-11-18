from typing import Any


def f(o: Any) -> object:
    return getattr(o, "formula")


def g(o: Any) -> object:
    return o.formula
