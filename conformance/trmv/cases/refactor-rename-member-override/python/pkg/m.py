class Base:
    def old(self) -> int:
        return 1


class Sub(Base):
    def old(self) -> int:
        return 2


def f(b: Base) -> int:
    return b.old()
