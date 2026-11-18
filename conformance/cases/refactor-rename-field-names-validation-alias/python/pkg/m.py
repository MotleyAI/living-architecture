from pydantic import BaseModel, Field, field_validator


class Ds(BaseModel):
    columns: list[str] = Field(validation_alias="cols")

    @field_validator("columns")
    @classmethod
    def _v(cls, v: list[str]) -> list[str]:
        return v
