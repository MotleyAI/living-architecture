from pkg.errors import A, B, C
from pkg.shapes import K, N1, N2, Ov, Ov2


def f() -> None:
    raise A("x", field="a")


def g() -> None:
    raise B("y", field="b")


def h() -> list[object]:
    return [
        C("z", field="c"),
        N1(field="a"),
        N2(field="b"),
        Ov(field="a"),
        Ov(field=1),
        Ov2(field="b"),
        K(field="a"),
    ]
