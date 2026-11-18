from pydantic import BaseModel
from pydantic import field_validator as fv


class Ds(BaseModel):
    columns: list[str]

    @fv("columns")
    @classmethod
    def _v(cls, v: list[str]) -> list[str]:
        return v
