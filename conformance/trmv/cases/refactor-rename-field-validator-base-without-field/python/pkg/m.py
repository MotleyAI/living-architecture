from pydantic import BaseModel, field_validator


class Base(BaseModel):
    @field_validator("columns", check_fields=False)
    @classmethod
    def _base(cls, v: list[str]) -> list[str]:
        return v


class Ds(Base):
    columns: list[str]

    @field_validator("columns")
    @classmethod
    def _own(cls, v: list[str]) -> list[str]:
        return v
