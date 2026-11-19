class Slotted:
    __slots__ = ("fields",)

    def __init__(self) -> None:
        self.fields: list[str] = []


def make() -> list[str]:
    return Slotted().fields
