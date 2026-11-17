class Default[T = int]:
    item: T


def pick[U = str](value: U) -> U:
    return value


type Listed[V = int] = list[V]
