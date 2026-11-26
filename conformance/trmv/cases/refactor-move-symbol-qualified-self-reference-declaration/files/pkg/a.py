import pkg.a


def f(n, step=lambda k: pkg.a.f(k), first=pkg.a.f):
    return pkg.a.f(n - 1) if n else 0


def g():
    return 1
