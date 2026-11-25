from typing import Optional


class Rec:
    pass


def make() -> "Rec":
    return Rec()


def opt(a: Optional["Rec"], b: list["Rec"], c: "Rec | None", d: 'Rec | None') -> None: ...
