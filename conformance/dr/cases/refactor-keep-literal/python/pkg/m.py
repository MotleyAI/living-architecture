from pydantic import BaseModel


class Member(BaseModel):
    type: str = ""


class Ds(BaseModel):
    columns: list[Member] = []
