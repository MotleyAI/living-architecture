import sys
from pkg.a import g
from pkg.b import f
import os


def test_sym_multi_name() -> None:
    assert f() + g() and os.sep and sys.path
