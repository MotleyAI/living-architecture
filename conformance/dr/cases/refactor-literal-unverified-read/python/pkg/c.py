from typing import Literal

Kind2 = Literal["formula", "sql"]
DISPATCH_FORMULA = "formula"


def via_constant() -> Kind2:
    return DISPATCH_FORMULA


def matches(doc: dict[str, str]) -> bool:
    return doc["kind"] == DISPATCH_FORMULA
