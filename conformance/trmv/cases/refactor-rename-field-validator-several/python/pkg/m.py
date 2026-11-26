from pydantic import BaseModel, field_validator


class Ds(BaseModel):
    name: str
    columns: list[str]

    @field_validator("name", "columns", mode="before")
    @classmethod
    def _v(cls, v: object) -> object:
        return v

    @field_validator("*")
    @classmethod
    def _all(cls, v: object) -> object:
        return v
