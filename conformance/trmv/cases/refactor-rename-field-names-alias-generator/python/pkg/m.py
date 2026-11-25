from pydantic import BaseModel, ConfigDict, field_validator


class Ds(BaseModel):
    model_config = ConfigDict(alias_generator=str.upper)

    columns: list[str]

    @field_validator("columns")
    @classmethod
    def _v(cls, v: list[str]) -> list[str]:
        return v
