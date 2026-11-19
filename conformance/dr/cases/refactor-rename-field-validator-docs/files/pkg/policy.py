from pydantic import BaseModel, field_validator


class Rule(BaseModel):
    path: tuple[str, ...]

    @field_validator("path")
    @classmethod
    def _non_empty(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if not v:
            raise ValueError("Rule.path must be non-empty")
        return v
