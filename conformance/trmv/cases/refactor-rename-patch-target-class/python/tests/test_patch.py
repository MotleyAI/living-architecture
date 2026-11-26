from unittest.mock import patch

import pytest
from pytest_mock import MockerFixture


def test_targets(mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch) -> None:
    patch("pkg.engine.SearchQueryEngine.save_model")
    patch("pkg.SearchQueryEngine.save_model")
    mocker.patch("pkg.engine.SearchQueryEngine.save_model")
    monkeypatch.setattr("pkg.engine.SearchQueryEngine.save_model", None)
    monkeypatch.delattr('pkg.SearchQueryEngine.save_model')
