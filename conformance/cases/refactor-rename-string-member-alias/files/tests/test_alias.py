from builtins import getattr as read
from unittest.mock import patch as mock_patch

from pkg.engine import Engine


def test_alias(engine: Engine) -> None:
    read(engine, "persist_model")
    with mock_patch.object(Engine, "persist_model"):
        pass
