"""B."""
import pkg.a


def f(n, step=lambda k: f(k), first=pkg.a.f):
    return f(n - 1) if n else 0
