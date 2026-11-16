from unittest.mock import patch

from pkg.mod import Model


def read(m: Model) -> list[int]:
    return m.columns


def build() -> Model:
    return Model(columns=[])


def parse() -> Model:
    return Model.model_validate({"columns": []})


def dynamic(m: Model) -> object:
    return getattr(m, "columns")


def patched() -> None:
    with patch.object(Model, "columns"):
        pass
    with patch("pkg.mod.Model.columns"):
        pass
