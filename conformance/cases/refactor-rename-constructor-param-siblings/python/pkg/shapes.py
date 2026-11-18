from typing import overload


class N1:
    def __new__(cls, *, field: str) -> "N1":
        print(field)
        return super().__new__(cls)


class N2:
    def __new__(cls, *, field: str) -> "N2":
        print(field)
        return super().__new__(cls)


class Ov:
    @overload
    def __init__(self, *, field: str) -> None: ...
    @overload
    def __init__(self, *, field: int) -> None: ...
    def __init__(self, *, field: str | int) -> None:
        self.value = field


class Ov2:
    def __init__(self, *, field: str) -> None:
        self.value = field


class K:
    def __new__(cls, *, field: str) -> "K":
        return super().__new__(cls)

    def __init__(self, *, field: str) -> None:
        self.value = field
