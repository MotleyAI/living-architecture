import typing as t


def f(t):
    if t.TYPE_CHECKING:
        import pkg.core
