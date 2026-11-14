from unittest.mock import patch

import pytest
from pytest_mock import MockerFixture

from pkg.engine import SlayerQueryEngine


class Sub(SlayerQueryEngine):
    pass


def test_forms(engine: SlayerQueryEngine, sub: Sub, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture) -> None:
    patch.object(SlayerQueryEngine, "save_model")
    monkeypatch.setattr(engine, "save_model", lambda name: None)
    mocker.patch.object(engine, 'save_model')
    getattr(engine, "save_model")
    setattr(sub, "save_model", None)
    hasattr(type(engine), "save_model")
    delattr(Sub, "save_model")
    getattr(engine, f"save_model")
    getattr(engine, "save_model_x")
