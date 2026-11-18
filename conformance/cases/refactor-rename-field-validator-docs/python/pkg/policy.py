from pydantic import BaseModel, field_validator


class Rule(BaseModel):
    join_path: tuple[str, ...]

    @field_validator("join_path")
    @classmethod
    def _non_empty(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if not v:
            raise ValueError("Rule.join_path must be non-empty")
        return v
