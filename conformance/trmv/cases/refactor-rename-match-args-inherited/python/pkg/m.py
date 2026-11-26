class Base:
    def __init__(self, name: str, columns: list[str]) -> None:
        self.name = name
        self.columns = columns


class Sub(Base):
    __match_args__ = ("name", "columns")


def read(b: Base) -> list[str]:
    match b:
        case Sub(_, columns):
            return columns
        case _:
            return []
