from pydantic import BaseModel, Field, field_validator


class Ds(BaseModel):
    fields: list[str] = Field(validation_alias="cols")

    @field_validator("fields")
    @classmethod
    def _v(cls, v: list[str]) -> list[str]:
        return v
