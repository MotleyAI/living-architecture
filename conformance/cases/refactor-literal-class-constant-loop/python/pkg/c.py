from typing import Literal

Kind2 = Literal["formula", "sql"]


def take(k: Kind2) -> None:
    print(k)
