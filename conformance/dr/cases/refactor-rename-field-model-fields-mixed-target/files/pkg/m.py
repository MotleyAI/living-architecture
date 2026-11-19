from pydantic import BaseModel


class Ds(BaseModel):
    columns: list[str]


class Other(BaseModel):
    columns: list[int]


def read(m: Ds | Other) -> object:
    return m.model_fields["columns"]
