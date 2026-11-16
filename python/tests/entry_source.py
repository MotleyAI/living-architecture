"""The module the entry-location tests locate in, and positions in it."""

M = '''\
from pkg import other
from pkg.other import thing
from typing import overload

try:
    from pkg.other import thing as either
except ImportError:
    from pkg.alt import either


def top(a, /, b, *args, c, **kwargs):
    local = a
    local += 1
    ann: int = 2
    if (walrus := b):
        pass
    for loop_var in args:
        pass
    with open("x") as handle:
        pass
    try:
        pass
    except ValueError as err:
        pass
    match c:
        case [matched]:
            pass
    squares = [comp_var for comp_var in args]
    fn = lambda lam_arg: lam_arg
    return local, ann, walrus, loop_var, handle, err, matched, squares, fn, kwargs


COUNTER = 0


def bump():
    global COUNTER
    COUNTER += 1


def outer():
    shared = 1

    def inner():
        nonlocal shared
        shared = 2

    return inner


class Box:
    size: int = 0

    def __init__(self) -> None:
        self.weight = 1

    @property
    def label(self) -> str:
        return ""

    @label.setter
    def label(self, value: str) -> None:
        pass

    @overload
    def get(self, k: int) -> int: ...
    @overload
    def get(self, k: str) -> str: ...
    def get(self, k):
        return k


if COUNTER:
    MODE = 1
else:
    MODE = 2


def use(b: Box) -> object:
    return top(1, 2, c=3), b.size, len([]), thing, other.thing, MODE, either, nowhere
'''
OTHER = "thing = 1\n"
ALT = "either = 2\n"


def at(needle: str, nth: int = 0, inner: str | None = None) -> int:
    """The offset of `inner` (else `needle`) within the `nth` occurrence of `needle` in M."""
    offset = -1
    for _ in range(nth + 1):
        offset = M.index(needle, offset + 1)
    return offset + (needle.index(inner) if inner is not None else 0)


def line(needle: str, nth: int = 0) -> int:
    return M.count("\n", 0, at(needle, nth)) + 1
