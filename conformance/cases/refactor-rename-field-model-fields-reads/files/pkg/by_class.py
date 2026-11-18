from pkg.m import Ds


def reads() -> list[object]:
    return [
        Ds.model_fields["fields"],
        Ds.model_fields.get("fields"),
        "fields" in Ds.model_fields,
    ]
