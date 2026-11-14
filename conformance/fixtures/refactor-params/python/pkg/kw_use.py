import functools

from pkg.kw import kwonly, posonly, star


def wrap(**kw: str) -> str:
    return kwonly(**kw)


def calls() -> list[object]:
    return [
        kwonly(model_name="x"),
        star(1, 2, model_name="x"),
        posonly("x"),
        kwonly(**{"model_name": "x"}),
        wrap(model_name="x"),
        functools.partial(kwonly, model_name="x"),
    ]
