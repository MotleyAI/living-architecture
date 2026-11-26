from pydantic import BaseModel


class Model(BaseModel):
    columns: list[int] = []
