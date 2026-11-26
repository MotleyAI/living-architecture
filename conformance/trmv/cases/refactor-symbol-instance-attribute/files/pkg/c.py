class C:
    def __init__(self) -> None:
        self.store = {}

    def size(self) -> int:
        return len(self.store)


def peek(c: C) -> int:
    return len(c.store)
