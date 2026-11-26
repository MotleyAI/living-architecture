class C:
    def __init__(self) -> None:
        self.cache = {}

    def size(self) -> int:
        return len(self.cache)


def peek(c: C) -> int:
    return len(c.cache)
