from typing import Literal, Optional


class Foo:
    peer: "Foo | None"


def f(a: "Foo", b: "Optional[Foo]" = None) -> "list[Foo]":
    return [a]


x: "Foo"
y: Literal["Foo", "Bar"] = "Foo"
z: r"Foo"
w: "Fo" "o"
v: "  Foo  "
u: "Foo[" = None
