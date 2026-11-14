def use() -> object:
    return getattr(make(), "save_model")


class Engine:
    def save_model(self) -> None:
        pass


def make() -> Engine:
    return Engine()


X = getattr(make(), "save_model")
