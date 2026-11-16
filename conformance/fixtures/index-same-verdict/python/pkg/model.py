from typing import Any


class Model:
    formula: str = ""


def typed(m: Model) -> str:
    return m.formula


def untyped(m):
    return m.formula


def anyone(o: Any) -> str:
    return o.formula


def mixed(m: Model | Any) -> str:
    return (
        m
    ).formula


def dynamic(m) -> object:
    return getattr(m, "formula")
