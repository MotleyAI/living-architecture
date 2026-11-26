from typing import Protocol


class I(Protocol):
    def old(self) -> int: ...


class C(I):
    def old(self) -> int:
        return 1


def f(i: I) -> int:
    return i.old()
