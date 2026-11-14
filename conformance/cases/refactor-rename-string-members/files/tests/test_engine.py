from unittest.mock import patch

import pytest
from pytest_mock import MockerFixture

from pkg.engine import SlayerQueryEngine


class Sub(SlayerQueryEngine):
    pass


def test_forms(engine: SlayerQueryEngine, sub: Sub, monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture) -> None:
    patch.object(SlayerQueryEngine, "persist_model")
    monkeypatch.setattr(engine, "persist_model", lambda name: None)
    mocker.patch.object(engine, 'persist_model')
    getattr(engine, "persist_model")
    setattr(sub, "persist_model", None)
    hasattr(type(engine), "persist_model")
    delattr(Sub, "persist_model")
    getattr(engine, f"save_model")
    getattr(engine, "save_model_x")
