from pkg.m import Ds


def reads() -> list[object]:
    return [
        Ds.model_fields["columns"],
        Ds.model_fields.get("columns"),
        "columns" in Ds.model_fields,
    ]
