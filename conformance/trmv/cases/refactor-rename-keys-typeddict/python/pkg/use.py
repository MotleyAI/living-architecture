from pkg.models import ModelDict


def f(d: ModelDict) -> None: ...


def g() -> ModelDict:
    return {"columns": []}


f({"columns": []})
x: ModelDict = {"columns": []}
