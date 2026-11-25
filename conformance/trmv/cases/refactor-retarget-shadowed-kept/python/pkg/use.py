from pkg.models import AcmeModel


def make() -> object:
    Model = 1
    return Model, AcmeModel()


def other() -> object:
    return AcmeModel()
