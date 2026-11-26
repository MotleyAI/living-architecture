class Base:
    __slots__ = ("name",)

    def __init__(self) -> None:
        self.name = ""


class Wide(Base):
    __slots__ = Base.__slots__ + ("columns",)
    __match_args__ = ("fields",)

    def __init__(self) -> None:
        super().__init__()
        self.fields: list[str] = []
