class Base:
    def ping(self) -> int:
        return 1


class Sub(Base):
    def ping(self) -> int:
        return 2


class Base2:
    def pong(self) -> int:
        return 3


class Sub2(Base2):
    def pong(self) -> int:
        return 4
