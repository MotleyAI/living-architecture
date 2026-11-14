from typing import Any

from missing_lib import untyped_call


class Model:
    formula: str = ""


def typed(x: Model, xs: list[Model]) -> list[str]:
    return [x.formula, *(i.formula for i in xs)]
