from collections.abc import Iterator
from contextlib import contextmanager


class Ds:
    def __init__(self) -> None:
        self.columns: list[str] = []
        self.name: str = ""


def parameter(d: Ds, s: str) -> object:
    return getattr(d, s)


def caller(d: Ds) -> object:
    return parameter(d, "columns")


def branches(d: Ds, flag: bool) -> object:
    if flag:
        s = "columns"
    else:
        s = "name"
    return getattr(d, s)


def unpacked(d: Ds) -> object:
    s, t = "columns", "name"
    return getattr(d, s), getattr(d, t)


def walrus(d: Ds) -> object:
    print(s := "columns")
    return getattr(d, s)


def appended(d: Ds) -> list[object]:
    names = ["columns"]
    names.append("name")
    return [getattr(d, s) for s in names]


def frozen(d: Ds) -> list[object]:
    return [getattr(d, s) for s in frozenset({"columns"})]


def augmented(d: Ds) -> object:
    s = "columns"
    s += ""
    return getattr(d, s)


@contextmanager
def chosen() -> Iterator[str]:
    yield "columns"


def managed(d: Ds) -> object:
    with chosen() as s:
        return getattr(d, s)


def declared_global(d: Ds) -> object:
    global CHOSEN
    CHOSEN = "columns"
    return getattr(d, CHOSEN)


def declared_nonlocal(d: Ds) -> object:
    s = "name"

    def pick() -> None:
        nonlocal s
        s = "columns"

    pick()
    return getattr(d, s)
