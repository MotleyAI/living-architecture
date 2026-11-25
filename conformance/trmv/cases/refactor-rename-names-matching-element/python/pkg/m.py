class Ds:
    def __init__(self) -> None:
        self.columns: list[str] = []
        self.label: str = ""


FIELDS = ("label", "columns")


def read(d: Ds) -> list[object]:
    out: list[object] = []
    for f in FIELDS:
        out.append(getattr(d, f))
    return out
