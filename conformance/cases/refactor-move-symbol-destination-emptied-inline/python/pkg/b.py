from typing import TYPE_CHECKING

if TYPE_CHECKING: from pkg.a import f


def g() -> "f":
    return 1
