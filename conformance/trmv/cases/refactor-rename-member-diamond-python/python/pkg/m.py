class A:
    def old(self) -> int:
        return 1


class B:
    def old(self) -> int:
        return 2


class D(A, B):
    pass


def f(d: D) -> int:
    return d.old()
