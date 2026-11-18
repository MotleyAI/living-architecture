def f(a: int, b: int) -> int:
    return a + b


def use() -> int:
    return f(1, "x") + len(3)


def other() -> int:
    return 1
