class K:
    def __new__(cls, *, field: str) -> "K":
        return super().__new__(cls)

    def __init__(self, *, field: str) -> None:
        self.value = field


def use() -> K:
    return K(field="a")
