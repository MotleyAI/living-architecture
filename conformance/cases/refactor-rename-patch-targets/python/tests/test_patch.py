from unittest.mock import patch

import pytest
from pytest_mock import MockerFixture


def test_targets(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    patch("pkg.engine.AcmeQueryEngine.save_model")
    patch("pkg.AcmeQueryEngine.save_model")
    mocker.patch("pkg.engine.AcmeQueryEngine.save_model")
    monkeypatch.setattr("pkg.engine.AcmeQueryEngine.save_model", None)
    monkeypatch.delattr('pkg.AcmeQueryEngine.save_model')
