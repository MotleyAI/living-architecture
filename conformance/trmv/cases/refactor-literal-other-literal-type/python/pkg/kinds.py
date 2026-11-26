from typing import Literal

DriftKind = Literal["edit_model", "drop"]
Other = Literal["edit_model", "zzz"]


def f(kind: DriftKind) -> None:
    print(kind)


def g(o: Other) -> None:
    print(o)
