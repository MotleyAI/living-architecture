from unittest.mock import MagicMock


def f(a, b: int, *args, c, **kw):
    return a


def g() -> None:
    pass


class K:
    declared: int

    def __init__(self, x: int) -> None:
        self.x = x
        self.declared = 1
        self.y: str = ''
        self.z = 2
        self.z = 3

    @classmethod
    def make(cls, v):
        return cls(v)

    async def run(self, item) -> None:
        item.name = 1
        print(item.name)


m = MagicMock()
