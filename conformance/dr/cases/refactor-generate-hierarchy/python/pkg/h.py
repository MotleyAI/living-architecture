class Base:
    def measures(self) -> int:
        return 1


class Sub(Base):
    def measures(self) -> int:
        return 2
