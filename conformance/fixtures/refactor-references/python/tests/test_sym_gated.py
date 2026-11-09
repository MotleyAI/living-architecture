import pytest

yaml = pytest.importorskip("yaml")
import yaml.constructor
from pkg.a import f


def test_sym_gated() -> None:
    assert f() and yaml.constructor
