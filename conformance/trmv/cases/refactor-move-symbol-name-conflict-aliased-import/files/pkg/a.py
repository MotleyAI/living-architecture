"""Source module."""

import os
import sys

__all__ = ["f", "g"]


def f() -> str:
    return os.sep + sys.platform


def g() -> str:
    return f() + sys.version
