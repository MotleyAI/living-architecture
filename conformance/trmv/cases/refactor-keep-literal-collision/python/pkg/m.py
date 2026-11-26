from pydantic import BaseModel


class Ds(BaseModel):
    columns: list[str] = []
