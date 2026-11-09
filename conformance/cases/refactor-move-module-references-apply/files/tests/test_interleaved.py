import sys

sys.path.insert(0, ".")

from pkg.database.client import X
import os


def test_interleaved() -> None:
    assert X == 1 and os.sep and sys.path
