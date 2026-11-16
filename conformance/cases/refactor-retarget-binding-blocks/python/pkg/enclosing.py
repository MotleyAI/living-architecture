from pkg.models import Model


def make() -> object:
    from pkg.compat import AcmeModel
    return AcmeModel(), Model
