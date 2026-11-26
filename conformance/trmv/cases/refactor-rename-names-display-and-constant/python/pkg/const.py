from pkg.m import Ds

NAME = "columns"


def read(d: Ds) -> object:
    return getattr(d, NAME)
