class Slotted:
    __slots__ = ("columns",)

    def __init__(self) -> None:
        self.columns: list[str] = []


class Unrelated:
    __slots__ = ("columns",)

    def __init__(self) -> None:
        self.columns: list[int] = []
