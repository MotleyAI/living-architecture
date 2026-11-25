from pkg.m import Ds


def clear(d: Ds) -> None:
    for s in ("columns", "name"):
        setattr(d, s, None)
