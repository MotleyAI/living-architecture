from unittest.mock import patch

import pytest

from pkg import mod


def test_a(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "list_models", lambda: ["x"])
    with patch.object(mod, "list_models", return_value=[]):
        pass
    with patch("pkg.mod.list_models", return_value=[]):
        pass
