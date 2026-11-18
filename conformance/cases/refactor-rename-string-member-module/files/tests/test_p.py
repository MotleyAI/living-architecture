from unittest.mock import patch

import pytest

from pkg import mod


def test_a(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "list_datasets", lambda: ["x"])
    with patch.object(mod, "list_datasets", return_value=[]):
        pass
    with patch("pkg.mod.list_datasets", return_value=[]):
        pass
