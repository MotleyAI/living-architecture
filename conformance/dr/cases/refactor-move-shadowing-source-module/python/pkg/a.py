def f() -> int:
    return 1


g = lambda f: f()


def h(*, f):
    return f()
