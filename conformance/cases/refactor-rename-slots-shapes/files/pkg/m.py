class One:
    __slots__ = "fields"

    def __init__(self) -> None:
        self.fields: list[str] = []


class Listed:
    __slots__ = ["name", "fields"]

    def __init__(self) -> None:
        self.name = "columns of a table"
        self.fields: list[str] = []


class Keyed:
    __slots__ = {"fields": "the columns"}

    def __init__(self) -> None:
        self.fields: list[str] = []
