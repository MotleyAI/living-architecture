class One:
    __slots__ = "columns"

    def __init__(self) -> None:
        self.columns: list[str] = []


class Listed:
    __slots__ = ["name", "columns"]

    def __init__(self) -> None:
        self.name = "columns of a table"
        self.columns: list[str] = []


class Keyed:
    __slots__ = {"columns": "the columns"}

    def __init__(self) -> None:
        self.columns: list[str] = []
