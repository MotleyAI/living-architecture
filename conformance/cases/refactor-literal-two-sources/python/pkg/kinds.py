from typing import Literal

DriftKind = Literal["edit_model", "drop"]


def f(kind: DriftKind) -> None:
    print(kind)
