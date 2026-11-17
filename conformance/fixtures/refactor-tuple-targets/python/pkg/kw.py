def g(x: int = 0) -> int:
    return x


def h() -> int:
    a, x = 1, 5
    return g(x=1) + x
