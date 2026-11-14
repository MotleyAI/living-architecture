class Box:
    def __init__(self) -> None:
        self._size = 0

    @property
    def volume(self) -> int:
        return self._size

    @volume.setter
    def volume(self, value: int) -> None:
        self._size = value


def grow(b: Box) -> None:
    b.volume = b.volume + 1
