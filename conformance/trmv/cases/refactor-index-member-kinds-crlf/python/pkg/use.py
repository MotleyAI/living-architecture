from unittest.mock import patch

from pkg.mod import Model


def read(m: Model) -> list[int]:
    s = "😀"; return m.columns


def build() -> Model:
    s = "𝒳😀"; return Model(columns=[])


def parse() -> Model:
    s = "😀"; t = 1    return Model.model_validate({"😀": [], "columns": []})


def dynamic(m: Model) -> object:
    s = "😀"; return getattr(m, "columns")


def patched() -> None:
    s = "😀"; p = patch.object(Model, "columns")
    s = "😀"; q = patch("pkg.mod.Model.columns")