def f(a: int, /, b: int, *xs: int, c: int = 0, **kw: int) -> int:
    return a + b + sum(xs) + c + sum(kw.values())


def g(a: int, /, *args: int, **kwargs: int) -> None:
    print(a, args, kwargs)
