from collections.abc import Callable


def first[T](items: list[T]) -> T:
    return items[0]


class Box[T: int, *Ts, **P]:
    item: T

    def call(self, f: Callable[P, T]) -> T:
        return f


type Alias[K] = dict[K, Box[int]]
type Plain = int
