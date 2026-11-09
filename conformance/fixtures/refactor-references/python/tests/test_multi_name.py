import sys
from pkg.sql import dialects, client
import os


def test_multi_name() -> None:
    assert client.X and dialects.D and os.sep and sys.path
