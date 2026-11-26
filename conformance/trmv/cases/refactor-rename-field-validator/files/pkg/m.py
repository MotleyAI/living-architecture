from pydantic import BaseModel, field_validator


class Ds(BaseModel):
    fields: list[str]

    @field_validator("fields")
    @classmethod
    def _v(cls, v: list[str]) -> list[str]:
        return v

    @field_validator('fields')
    @classmethod
    def _w(cls, v: list[str]) -> list[str]:
        return v


def uses(d: Ds) -> list[str]:
    return d.fields
