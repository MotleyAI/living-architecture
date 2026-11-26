class Ds:
    def __init__(self) -> None:
        self.columns: list[str] = []


class Other:
    def __init__(self) -> None:
        self.columns: list[int] = []


SECTIONS = ("columns",)


def fill(o: Other) -> dict[str, int]:
    doc: dict[str, int] = {}
    for s in SECTIONS:
        doc[s] = len(getattr(o, s))
    return doc
