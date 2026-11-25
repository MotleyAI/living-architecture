class Ds:
    def __init__(self) -> None:
        self.columns: list[str] = []


SECTIONS = ("columns",)


def read(d: Ds) -> list[object]:
    return [getattr(d, s) for s in SECTIONS]
