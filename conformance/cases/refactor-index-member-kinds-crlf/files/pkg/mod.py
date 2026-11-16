from pydantic import BaseModel


class Model(BaseModel):
    s: str = "😀é𝒳"; fields: list[int] = []
