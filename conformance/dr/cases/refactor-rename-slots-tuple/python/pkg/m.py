class Slotted:
    __slots__ = ("columns",)

    def __init__(self) -> None:
        self.columns: list[str] = []


def make() -> list[str]:
    return Slotted().columns
