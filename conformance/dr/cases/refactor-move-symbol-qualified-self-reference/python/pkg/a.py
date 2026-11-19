import pkg.a


def f(n):
    return pkg.a.f(n - 1) if n else 0


def g():
    return 1
