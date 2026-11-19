from pydantic import BaseModel, field_validator


class Ds(BaseModel):
    columns: list[str]

    @field_validator("columns", "fields", check_fields=False)
    @classmethod
    def _v(cls, v: list[str]) -> list[str]:
        return v
