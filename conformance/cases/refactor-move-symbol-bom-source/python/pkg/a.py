import os


def f() -> str:
    return os.sep


def g() -> str:
    return f()
