from pydantic import BaseModel


class Model(BaseModel):
    s: str = "😀é𝒳"; columns: list[int] = []
