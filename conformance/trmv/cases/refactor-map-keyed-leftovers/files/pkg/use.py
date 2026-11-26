from pkg.models import A, B


def use() -> object:
    return (
        A(fields=[]),
        B(cols=[]),
        A.model_validate({"fields": []}),
        B.model_validate({"cols": []}),
    )
