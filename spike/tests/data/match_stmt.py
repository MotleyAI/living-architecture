class Point:
    __match_args__ = ("x", "y")

    def __init__(self, x: int, y: int) -> None:
        self.x, self.y = x, y


def describe(subject: object) -> str:
    match subject:
        case [1, *rest]:
            return str(rest)
        case {"k": v, **others}:
            return str(v) + str(others)
        case Point(x=px) as p if px > 0:
            return str(p)
        case str() | bytes() as text:
            return str(text)
        case _:
            return "other"
