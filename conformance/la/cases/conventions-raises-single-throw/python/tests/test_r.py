import pytest
from pytest import raises


def test_a():
    with pytest.raises(ValueError):
        int(str(1))


def test_b():
    with raises(ValueError):
        int('x')


def test_c(self):
    with self.assertRaises(ValueError), open('f'):
        f(g(h()))


def test_d(self):
    with self.assertRaisesRegex(ValueError, 'x'):
        a()
        b()


async def test_e():
    async with pytest.raises(ValueError):
        await f(g())


def test_f():
    with open('x'):
        a(b())
