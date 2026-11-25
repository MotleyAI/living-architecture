from pkg.models import Model, Sub


def build(kind: type[Model]) -> list[Model]:
    return [Model(columns=[]), Sub(columns=[], extra=1), kind(columns=[])]
