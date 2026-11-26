from typing import Protocol, overload


class Shape:
    @overload
    def area(self, x: int) -> int: ...
    @overload
    def area(self, x: str) -> str: ...
    def area(self, x: int | str) -> int | str:
        return x


class Base:
    def sync_model(self, x: int) -> int:
        return x


class Child(Base):
    def sync_model(self, x: int) -> int:
        return super().sync_model(x)


class Store(Protocol):
    def fetch(self) -> int: ...


class Disk(Store):
    def fetch(self) -> int:
        return 1


def use(s: Shape, c: Child, st: Store, d: Disk) -> object:
    return (s.area(1), c.sync_model(2), st.fetch(), d.fetch())
