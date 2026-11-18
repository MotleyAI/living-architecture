from pydantic import BaseModel, field_validator


class Ds(BaseModel):
    name: str
    fields: list[str]

    @field_validator("name", "fields", mode="before")
    @classmethod
    def _v(cls, v: object) -> object:
        return v

    @field_validator("*")
    @classmethod
    def _all(cls, v: object) -> object:
        return v
