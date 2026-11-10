"""Destination module."""

import sys
import pytest
import os

yaml = pytest.importorskip("yaml")
import yaml.constructor


def f() -> str:
    return os.sep + sys.platform


def h() -> str:
    return f() + sys.prefix + str(yaml.constructor)
