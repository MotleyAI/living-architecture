__all__ = ["Rec", "make"]


class Rec:
    pass


x: "Rec | None" = None


def make() -> "Rec":
    return Rec()
