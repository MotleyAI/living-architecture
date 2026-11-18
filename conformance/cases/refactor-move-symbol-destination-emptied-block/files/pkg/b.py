from typing import TYPE_CHECKING


def f():
    return 1

if TYPE_CHECKING:
    pass


def g() -> "f":
    return 1
