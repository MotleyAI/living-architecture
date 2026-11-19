from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    columns: list[int] = Field(default=[], alias="cols")


class Gen(BaseModel):
    model_config = ConfigDict(alias_generator=str.upper)
    fields: list[int] = []


class Val(BaseModel):
    columns: list[int] = Field(default=[], validation_alias="cols")
