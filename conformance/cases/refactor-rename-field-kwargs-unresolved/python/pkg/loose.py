from typing import Any

from pkg.q import Other, Query


def alias(**kw: Any) -> Query:
    d = kw
    return Query(**d)


def copied(**kw: Any) -> Query:
    return Query(**dict(kw))


def copy_method(**kw: Any) -> Query:
    return Query(**kw.copy())


def updated(**kw: Any) -> Query:
    base: dict[str, Any] = {"source_model": "orders"}
    base.update(kw)
    return Query(**base)


def merged(**kw: Any) -> Query:
    base: dict[str, Any] = {"source_model": "orders"}
    return Query(**(base | kw))


def build(data: dict[str, Any]) -> Query:
    return Query(**data)


def plain_argument(**kw: Any) -> Query:
    return build(kw)


def returned(**kw: Any) -> dict[str, Any]:
    return kw


def iterated(**kw: Any) -> Query:
    for key in kw:
        print(key)
    return Query(**kw)


def items(**kw: Any) -> Query:
    print(kw.items())
    return Query(**kw)


def variable_key(name: str, **kw: Any) -> Query:
    print(kw[name])
    return Query(**kw)


def rebound(**kw: Any) -> Query:
    kw = {**kw, "source_model": "orders"}
    return Query(**kw)


def nested(**kw: Any) -> Query:
    def inner() -> Query:
        return Query(**kw)

    return inner()


def ping(**kw: Any) -> Query:
    return pong(**kw)


def pong(**kw: Any) -> Query:
    return ping(**kw)


def both(**kw: Any) -> tuple[Query, Other]:
    return Query(**kw), Other(**kw)
