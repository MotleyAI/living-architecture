class P:
    def __init__(self) -> None:
        self._v = 0

    @property
    def value(self) -> int:
        return self._v

    @value.setter
    def value(self, v: int) -> None:
        self._v = v


class Q(P):
    @property
    def value(self) -> int:
        return 5


def use(p: P, q: Q) -> int:
    p.value = 3
    return p.value + q.value
