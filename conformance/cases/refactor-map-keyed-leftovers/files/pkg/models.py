from pydantic import BaseModel


class A(BaseModel):
    fields: list[int] = []


class B(BaseModel):
    cols: list[int] = []
