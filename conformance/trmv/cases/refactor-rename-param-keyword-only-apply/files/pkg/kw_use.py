import functools

from pkg.kw import kwonly, posonly, star


def wrap(**kw: str) -> str:
    return kwonly(**kw)


def calls() -> list[object]:
    return [
        kwonly(dataset_name="x"),
        star(1, 2, model_name="x"),
        posonly("x"),
        kwonly(**{"dataset_name": "x"}),
        wrap(dataset_name="x"),
        functools.partial(kwonly, dataset_name="x"),
    ]
