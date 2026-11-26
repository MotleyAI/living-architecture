"""Source module."""

import sys
from pkg.b import f

__all__ = ["g"]


def g() -> str:
    return f() + sys.version
