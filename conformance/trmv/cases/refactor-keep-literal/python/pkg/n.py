from pkg.m import Ds


def stored() -> Ds:
    doc = {"version": 3, "columns": []}
    return Ds.model_validate(doc)


def documents() -> list[Ds]:
    return [
        Ds.model_validate({"version": 3, "columns": [{"type": "INT"}]}),
        Ds.model_validate({"columns": [{"version": 1, "type": "INT"}, {"type": "TEXT"}]}),
        Ds.model_validate({"columns": []}),
        Ds.model_validate({"versions": 1, "columns": []}),
        Ds.model_validate({"ver" "sion": 3, "columns": []}),
        Ds.model_validate({**{"version": 3}, "columns": []}),
    ]
