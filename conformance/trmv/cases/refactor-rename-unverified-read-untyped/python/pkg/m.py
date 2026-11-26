from typing import Any


class Ds:
    def __init__(self) -> None:
        self.columns: list[str] = []


SECTIONS = ("columns",)


def read(d: Ds, x: Any) -> list[object]:
    out: list[object] = []
    for s in SECTIONS:
        out.append(getattr(d, s))
        out.append(getattr(x, s))
    return out
