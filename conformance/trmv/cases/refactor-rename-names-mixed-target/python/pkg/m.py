class Ds:
    def __init__(self) -> None:
        self.columns: list[str] = []


class Other:
    def __init__(self) -> None:
        self.columns: list[int] = []


SECTIONS = ("columns",)


def read(d: Ds, o: Other) -> list[object]:
    out: list[object] = []
    for s in SECTIONS:
        out.append(getattr(d, s))
        out.append(getattr(o, s))
    return out
