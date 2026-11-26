from typing import Any

from missing_lib import thing


class Model:
    formula: str = ""


def u(x: Model | int, y: list, w: Model | Any) -> None:
    z = x if isinstance(x, Model) else y[0]
    print(z.formula, w.formula)
    print(y[
        0
    ].formula)
    print(thing.a.formula)
