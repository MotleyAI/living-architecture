from pkg.m import Ds, Other


def reads() -> list[object]:
    return [
        Ds.model_fields["columns"],
        Other.model_fields["columns"],
    ]
