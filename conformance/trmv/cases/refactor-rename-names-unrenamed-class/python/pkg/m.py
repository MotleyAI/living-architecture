class Ds:
    def __init__(self) -> None:
        self.columns: list[str] = []


class Other:
    def __init__(self) -> None:
        self.columns: list[int] = []


SECTIONS = ("columns",)


def read(o: Other) -> list[object]:
    return [getattr(o, s) for s in SECTIONS]
