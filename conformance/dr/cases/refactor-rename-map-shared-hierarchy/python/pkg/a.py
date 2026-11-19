class Base:
    def items(self) -> int:
        return 0


class Sub(Base):
    def items(self) -> int:
        return 1


class Client:
    def items(self) -> int:
        return 2


def use(b: Base, c: Client) -> int:
    return b.items() + c.items()
