from typing import Any

from pydantic import BaseModel


class Query(BaseModel):
    source_model: str
    measures: list[str] = []


class Other(BaseModel):
    measures: list[int] = []


class Sub(Query):
    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)


def q(**kw: Any) -> Query:
    kw.setdefault("source_model", "orders")
    if "source_model" in kw:
        print(kw["source_model"], kw.get("source_model"))
    kw["source_model"] = kw.pop("source_model", None) or "orders"
    return Query(**kw)


def q2(**kw: Any) -> Query:
    return q(**kw)


def lit(**kw: Any) -> Query:
    return Query(**{"source_model": "orders", **kw})


def bound(**kw: Any) -> Query:
    data = {"source_model": "orders", **kw}
    return Query.model_validate(data)


def shadow(**kw: Any) -> Query:
    print([kw for kw in ("a", "b")], (lambda kw: kw)(1))
    return Query(**kw)


def other(**kw: Any) -> Other:
    return Other(**kw)
