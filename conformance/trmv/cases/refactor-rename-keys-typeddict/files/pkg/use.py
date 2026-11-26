from pkg.models import ModelDict


def f(d: ModelDict) -> None: ...


def g() -> ModelDict:
    return {"fields": []}


f({"fields": []})
x: ModelDict = {"fields": []}
