"""Rows carry ``field``."""
# field is plain here


class A:
    field: str = ""


class Helper:
    """Formats ``field`` values."""


def show(a: A) -> str:
    """Returns ``field``."""
    return a.field
