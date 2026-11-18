from pkg.m import Ds


def stored() -> Ds:
    doc = {"version": 3, "columns": []}
    return Ds.model_validate(doc)


def documents() -> list[Ds]:
    return [
        Ds.model_validate({"version": 3, "columns": [{"type": "INT"}]}),
        Ds.model_validate({"fields": [{"version": 1, "type": "INT"}, {"kind": "TEXT"}]}),
        Ds.model_validate({"fields": []}),
        Ds.model_validate({"versions": 1, "fields": []}),
        Ds.model_validate({"ver" "sion": 3, "fields": []}),
        Ds.model_validate({**{"version": 3}, "fields": []}),
    ]
