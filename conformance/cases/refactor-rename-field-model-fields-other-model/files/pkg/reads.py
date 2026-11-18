from pkg.m import Ds, Other


def reads() -> list[object]:
    return [
        Ds.model_fields["fields"],
        Other.model_fields["columns"],
    ]
