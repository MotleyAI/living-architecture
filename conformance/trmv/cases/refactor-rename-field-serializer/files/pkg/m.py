from pydantic import BaseModel, field_serializer


class Ds(BaseModel):
    fields: list[str]

    @field_serializer("fields")
    def _s(self, v: list[str]) -> list[str]:
        return v
