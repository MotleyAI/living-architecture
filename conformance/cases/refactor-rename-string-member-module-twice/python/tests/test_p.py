from unittest.mock import patch

from pkg import mod


def test_a() -> None:
    with patch.object(mod, "list_models", return_value=[]):
        pass
