from pydantic import BaseModel


class Ds(BaseModel):
    fields: list[str]


class Other(BaseModel):
    columns: list[int]
