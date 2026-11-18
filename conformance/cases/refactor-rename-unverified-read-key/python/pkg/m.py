class Ds:
    def __init__(self) -> None:
        self.columns: list[str] = []

    def size(self) -> int:
        return len(self.columns)


class Report:
    def __init__(self) -> None:
        self.rows: list[int] = []

    def add(self, n: int) -> None:
        self.rows.append(n)

    def total(self) -> int:
        return sum(self.rows)


SECTIONS = ("columns",)


def fill(d: Ds, report: Report) -> dict[str, int]:
    doc: dict[str, int] = {}
    for s in SECTIONS:
        value = getattr(d, s)
        if not value:
            continue
        report.add(len(value))
        report.add(d.size())
        doc[s] = 1
    return doc
