from typing import Any


def f(x: Any) -> object:
    return getattr(
        x[
            0
        ],
        "columns",
    )
