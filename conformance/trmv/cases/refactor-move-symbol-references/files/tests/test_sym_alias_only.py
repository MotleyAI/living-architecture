import sys
import pkg.b
import os


def test_sym_alias_only() -> None:
    assert pkg.b.f() and os.sep and sys.path
