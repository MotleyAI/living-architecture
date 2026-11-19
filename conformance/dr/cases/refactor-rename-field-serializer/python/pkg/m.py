from pydantic import BaseModel, field_serializer


class Ds(BaseModel):
    columns: list[str]

    @field_serializer("columns")
    def _s(self, v: list[str]) -> list[str]:
        return v
