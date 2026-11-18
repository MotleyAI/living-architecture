from pydantic import BaseModel, field_validator


class Ds(BaseModel):
    columns: list[str]

    @field_validator("columns")
    @classmethod
    def _v(cls, v: list[str]) -> list[str]:
        return v

    @field_validator('columns')
    @classmethod
    def _w(cls, v: list[str]) -> list[str]:
        return v


def uses(d: Ds) -> list[str]:
    return d.columns
