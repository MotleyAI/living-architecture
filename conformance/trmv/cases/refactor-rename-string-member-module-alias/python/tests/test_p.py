import pytest

import pkg.mod
import pkg.mod as m


def test_a(monkeypatch: pytest.MonkeyPatch) -> None:
    assert callable(getattr(m, "list_models"))
    monkeypatch.setattr(pkg.mod, "list_models", lambda: ["x"])
