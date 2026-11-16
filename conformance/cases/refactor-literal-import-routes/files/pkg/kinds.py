from typing import Literal

DriftKind = Literal["edit_master", "drop"]


def f(kind: DriftKind) -> None:
    print(kind)
