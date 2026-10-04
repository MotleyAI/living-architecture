import pytest


def test_x():
    assert 1 and 2
    with pytest.raises(ValueError):
        int(str(1))
