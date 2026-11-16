from pydantic import BaseModel


class A(BaseModel):
    columns: list[int] = []


class B(BaseModel):
    columns: list[int] = []
