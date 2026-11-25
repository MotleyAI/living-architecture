from pkg.models import Model, Sub


def build(kind: type[Model]) -> list[Model]:
    return [Model(fields=[]), Sub(fields=[], extra=1), kind(fields=[])]
