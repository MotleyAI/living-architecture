class Ds:
    def __init__(self) -> None:
        self.columns: list[str] = []


SECTIONS = ("columns",)


def fill(d: Ds) -> dict[str, int]:
    doc: dict[str, int] = {}
    for s in SECTIONS:
        doc[s] = len(getattr(d, s))
    return doc
