from pkg.m import Ds


def reads(d: Ds) -> list[object]:
    return [
        "fields" not in d.model_fields_set,
        type(d).model_fields["fields"],
    ]
