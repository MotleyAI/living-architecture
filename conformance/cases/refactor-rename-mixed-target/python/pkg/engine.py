class A:
    def save_model(self) -> int:
        return 1


class B:
    def save_model(self) -> int:
        return 2


def read(x: A | B) -> object:
    return getattr(x, "save_model")
