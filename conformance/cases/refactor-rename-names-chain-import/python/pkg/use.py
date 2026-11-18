from pkg.b import B
from pkg.m import Ds


def read(d: Ds) -> object:
    return getattr(d, B)
