from typing import Any, TypeVar

from pkg.models import Model, Other

T = TypeVar("T")


def a(u: Any) -> object:
    return u.model_validate({"columns": []})


def h(d: dict[str, Any]) -> None: ...


def b(m: Model | Other) -> object:
    return m.model_copy(update={"columns": []})


def c(kind: type[T]) -> T:
    return kind(**{"columns": []})


h({"columns": []})
