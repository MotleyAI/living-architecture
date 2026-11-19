from pkg.models import Model


def f() -> Model:
    raw = {"fields": []}
    return Model.model_validate(raw)
