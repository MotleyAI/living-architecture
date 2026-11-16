old = 1


def f() -> int:
    ys = [(next := x) for x in range(3)]
    return old + ys[0]
