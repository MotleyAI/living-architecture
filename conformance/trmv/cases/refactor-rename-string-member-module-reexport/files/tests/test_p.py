from unittest.mock import patch

import pkg


def test_a() -> None:
    with patch.object(pkg, "list_datasets", return_value=[]):
        pass
