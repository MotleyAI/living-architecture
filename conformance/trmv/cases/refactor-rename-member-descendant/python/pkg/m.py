class C:
    def old(self) -> int:
        return 1


class Sub(C):
    def next(self) -> int:
        return 2
