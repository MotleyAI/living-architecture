from typing import Any


def h(o: Any) -> object:
    return o.formula, getattr(o, "formula"), o.formula
