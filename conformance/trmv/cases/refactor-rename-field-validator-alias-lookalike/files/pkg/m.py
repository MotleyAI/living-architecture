from pydantic import BaseModel
from pydantic import field_validator as fv


class Ds(BaseModel):
    fields: list[str]

    @fv("fields")
    @classmethod
    def _v(cls, v: list[str]) -> list[str]:
        return v
