from pkg.mixed import f, g


def calls() -> None:
    f(1, 2, 3, c=4, d=5)
    f(1, b=2)
    f(1, 2, a=3)
    g(1, a=2, args=3, kwargs=4)
