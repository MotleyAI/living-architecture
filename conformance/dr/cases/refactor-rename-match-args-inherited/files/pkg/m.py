class Base:
    def __init__(self, name: str, columns: list[str]) -> None:
        self.name = name
        self.fields = columns


class Sub(Base):
    __match_args__ = ("name", "fields")


def read(b: Base) -> list[str]:
    match b:
        case Sub(_, columns):
            return columns
        case _:
            return []
