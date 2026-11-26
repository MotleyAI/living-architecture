from pkg.m import Ds


def both() -> Ds:
    return Ds.model_validate({"version": 3, "columns": [], "fields": []})


def plain() -> Ds:
    return Ds.model_validate({"columns": []})
