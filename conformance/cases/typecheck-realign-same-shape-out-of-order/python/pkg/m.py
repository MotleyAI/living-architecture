def f(a: int, b: int) -> int:
    return a + b


def use(v: str) -> int:
    a = len(3)
    b = f(1, "x")
    c = len(v)
    return a + b + c
