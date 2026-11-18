"""B."""


def f(n, step=lambda k: f(k)):
    return f(n - 1) if n else 0
