from typing import Optional, Sequence, TypedDict

from pydantic import BaseModel


class Member(BaseModel):
    name: str = ""
    type: str = "STR"


class Model(BaseModel):
    fields: list[Member] = []
    label: Optional[str] = None


class Sub(Model):
    extra: int = 0


class Other(BaseModel):
    columns: list[int] = []


class Holder(BaseModel):
    by_name: dict[str, Member] = {}
    maybe: Optional[Member] = None
    seq: Sequence[Member] = ()
    tup: tuple[Member, ...] = ()
    group: set[Member] = set()
    frozen: frozenset[Member] = frozenset()
    model: Model | None = None


class ModelDict(TypedDict):
    columns: list[int]
