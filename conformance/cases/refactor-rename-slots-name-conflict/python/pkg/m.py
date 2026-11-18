class Slotted:
    __slots__ = ("columns", "fields")  # pyright: ignore[reportUninitializedInstanceVariable]

    def __init__(self) -> None:
        self.columns: list[str] = []
