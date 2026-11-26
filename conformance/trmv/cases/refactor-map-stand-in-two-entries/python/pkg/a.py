class Table:
    columns: list[str] = []


class Result:
    columns: list[str] = []


class Other:
    columns: list[str] = []


def read(o: Other) -> list[str]:
    return o.columns
