from pkg.m import Ds


def local(d: Ds) -> object:
    key = "columns"
    return getattr(d, key)
