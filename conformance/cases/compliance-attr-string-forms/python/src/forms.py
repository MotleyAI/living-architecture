from unittest.mock import patch

import pytest


class Model:
    formula: str = ""


obj = Model()


def t(m) -> object:
    return getattr(m, "formula")


def u(monkeypatch) -> None:
    monkeypatch.setattr(obj, "formula", 1)


def w(o) -> None:
    patch.object(o, "formula")


def typed(m: Model, monkeypatch: pytest.MonkeyPatch) -> None:
    getattr(m, "formula")
    monkeypatch.setattr(m, "formula", "a")
