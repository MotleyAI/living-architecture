from pkg.models import helper


def make() -> object:
    from pkg.compat import AcmeModel
    return AcmeModel(), helper()
