try:
    from typing_extensions import Any
except ImportError:
    from typing import Any


class C:
    from typing import Any as A

    def m(self, x: A) -> None:
        y: A = x


def f() -> None:
    global Any
    z: Any = 1
w: Any
