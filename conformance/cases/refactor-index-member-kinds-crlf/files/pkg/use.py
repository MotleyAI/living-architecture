from unittest.mock import patch

from pkg.mod import Model


def read(m: Model) -> list[int]:
    s = "😀"; return m.fields


def build() -> Model:
    s = "𝒳😀"; return Model(fields=[])


def parse() -> Model:
    s = "😀"; t = 1    return Model.model_validate({"😀": [], "fields": []})


def dynamic(m: Model) -> object:
    s = "😀"; return getattr(m, "fields")


def patched() -> None:
    s = "😀"; p = patch.object(Model, "fields")
    s = "😀"; q = patch("pkg.mod.Model.fields")