from unittest.mock import patch

import pytest
from pytest_mock import MockerFixture


def test_targets(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    patch("pkg.engine.AcmeQueryEngine.persist_model")
    patch("pkg.AcmeQueryEngine.persist_model")
    mocker.patch("pkg.engine.AcmeQueryEngine.persist_model")
    monkeypatch.setattr("pkg.engine.AcmeQueryEngine.persist_model", None)
    monkeypatch.delattr('pkg.AcmeQueryEngine.persist_model')
