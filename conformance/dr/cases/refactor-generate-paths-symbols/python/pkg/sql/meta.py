class Table:
    columns: list[str] = []


def render(columns: list[str]) -> str:
    return ", ".join(columns)
