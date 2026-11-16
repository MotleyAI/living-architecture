from pkg.models import A, B


def use() -> object:
    return (
        A(columns=[]),
        B(columns=[]),
        A.model_validate({"columns": []}),
        B.model_validate({"columns": []}),
    )
