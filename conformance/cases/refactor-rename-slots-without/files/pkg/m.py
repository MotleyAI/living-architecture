class Slotted:
    __slots__ = ("fields",)

    def __init__(self) -> None:
        self.fields: list[str] = []


class Unrelated:
    __slots__ = ("columns",)

    def __init__(self) -> None:
        self.columns: list[int] = []
