from typing import Annotated, Any, Literal
x: "dict[str, Any]"
y: list["Any"]
z = []  # type: list[Any]
def f(a, b):
    # type: (Any, int) -> Any
    return a
l: Literal["Any"]
n: Annotated[int, "Any"]
i = 1  # type: ignore
w = []  # type: list[Any
