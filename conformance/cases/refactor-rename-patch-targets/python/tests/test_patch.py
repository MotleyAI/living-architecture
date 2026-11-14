from unittest.mock import patch

import pytest
from pytest_mock import MockerFixture


def test_targets(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    patch("pkg.engine.SlayerQueryEngine.save_model")
    patch("pkg.SlayerQueryEngine.save_model")
    mocker.patch("pkg.engine.SlayerQueryEngine.save_model")
    monkeypatch.setattr("pkg.engine.SlayerQueryEngine.save_model", None)
    monkeypatch.delattr('pkg.SlayerQueryEngine.save_model')
