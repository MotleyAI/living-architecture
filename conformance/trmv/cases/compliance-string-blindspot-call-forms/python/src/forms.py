from typing import Any
from unittest.mock import patch


def f(x: Any) -> None:
    getattr(x, "columns")
    setattr(x, "columns", 1)
    patch.object(x, "columns")
