from pydantic import BaseModel


class Member(BaseModel):
    kind: str = ""


class Ds(BaseModel):
    fields: list[Member] = []
