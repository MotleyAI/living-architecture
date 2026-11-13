from pydantic import BaseModel


class Model(BaseModel):
    columns: list[int] = []

    def describe(self) -> str:
        return ""
