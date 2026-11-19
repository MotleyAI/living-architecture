from pkg.models import Model


def f() -> Model:
    raw = {"columns": []}
    return Model.model_validate(raw)
