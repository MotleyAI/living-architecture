from typing import Optional


class Recommendation:
    pass


def make() -> "Recommendation":
    return Recommendation()


def opt(a: Optional["Recommendation"], b: list["Recommendation"], c: "Recommendation | None", d: 'Recommendation | None') -> None: ...
