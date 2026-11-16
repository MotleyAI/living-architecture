class Base:
    def run(self) -> int:
        return 1


def make():
    return Base


class Child(make()):  # pyright: ignore[reportUntypedBaseClass]
    def run(self) -> int:
        return 2
