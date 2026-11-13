from pkg.models import Model


def read() -> Model:
    raw = {"columns": []}
    print(raw["columns"])
    return Model.model_validate(raw)


def mutated() -> Model:
    raw = {"columns": []}
    raw["label"] = None
    return Model.model_validate(raw)


def captured() -> Model:
    raw = {"columns": []}
    g = lambda: raw
    return Model.model_validate(raw)


def unpacked() -> Model:
    raw = {"columns": []}
    other = {**raw}
    return Model.model_validate(raw)
