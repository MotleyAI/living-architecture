from pydantic import BaseModel


class Ds(BaseModel):
    fields: list[str] = []
