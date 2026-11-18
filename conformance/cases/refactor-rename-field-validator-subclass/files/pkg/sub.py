from pydantic import field_validator

from pkg.m import Ds


class Sub(Ds):
    extra: int = 0

    @field_validator("fields")
    @classmethod
    def _v(cls, v: list[str]) -> list[str]:
        return v
