from unittest.mock import patch

import pytest
from pytest_mock import MockerFixture


def test_targets(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    patch("pkg.engine.SearchQueryEngine.persist_model")
    patch("pkg.SearchQueryEngine.persist_model")
    mocker.patch("pkg.engine.SearchQueryEngine.persist_model")
    monkeypatch.setattr("pkg.engine.SearchQueryEngine.persist_model", None)
    monkeypatch.delattr('pkg.SearchQueryEngine.persist_model')
