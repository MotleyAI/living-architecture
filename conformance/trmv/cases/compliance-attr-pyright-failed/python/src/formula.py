from typing import Any

from missing_lib import untyped_call


class Model:
    formula: str = ""


def f(*, measures: list) -> list[object]:
    return [m.formula for m in measures]


def k() -> None:
    mdl = untyped_call()
    print(mdl.formula)
    hops = []
    print(list(map(lambda h: h.formula, hops)))


def g(o: Any) -> object:
    return o.formula


def typed(x: Model, xs: list[Model]) -> list[str]:
    return [x.formula, *(i.formula for i in xs)]
