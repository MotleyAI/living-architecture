from unittest.mock import patch

import pytest
from pytest_mock import MockerFixture


def test_targets(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    patch("pkg.engine.SlayerQueryEngine.persist_model")
    patch("pkg.SlayerQueryEngine.persist_model")
    mocker.patch("pkg.engine.SlayerQueryEngine.persist_model")
    monkeypatch.setattr("pkg.engine.SlayerQueryEngine.persist_model", None)
    monkeypatch.delattr('pkg.SlayerQueryEngine.persist_model')
