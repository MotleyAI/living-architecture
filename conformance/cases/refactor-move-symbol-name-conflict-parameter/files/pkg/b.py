"""Destination module."""

import sys
from pkg.a import f
import pytest

yaml = pytest.importorskip("yaml")
import yaml.constructor


def h() -> str:
    return f() + sys.prefix + str(yaml.constructor)
