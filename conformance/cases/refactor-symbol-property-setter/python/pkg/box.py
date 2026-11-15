class Box:
    def __init__(self) -> None:
        self._size = 0

    @property
    def size(self) -> int:
        return self._size

    @size.setter
    def size(self, value: int) -> None:
        self._size = value


def grow(b: Box) -> None:
    b.size = b.size + 1
