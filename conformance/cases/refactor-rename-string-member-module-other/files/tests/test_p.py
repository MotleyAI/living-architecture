from unittest.mock import patch

from pkg import mod, other


def test_a() -> None:
    with patch.object(other, "list_models", return_value=[]):
        pass
    with patch.object(mod, "list_datasets", return_value=[]):
        pass
