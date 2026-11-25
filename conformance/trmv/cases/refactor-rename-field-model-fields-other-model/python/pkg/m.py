from pydantic import BaseModel


class Ds(BaseModel):
    columns: list[str]


class Other(BaseModel):
    columns: list[int]
