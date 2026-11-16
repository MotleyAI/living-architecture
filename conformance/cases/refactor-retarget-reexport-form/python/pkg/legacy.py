from pkg.core import Model as OldModel

__all__ = ["OldModel"]


def make() -> object:
    return OldModel()
