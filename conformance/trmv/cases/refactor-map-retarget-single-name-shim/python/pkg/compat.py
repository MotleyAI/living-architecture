from pkg.models import AcmeModel

__all__ = ["AcmeModel"]


def make() -> object:
    return AcmeModel()
