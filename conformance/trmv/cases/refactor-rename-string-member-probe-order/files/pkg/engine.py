def use() -> object:
    return getattr(make(), "persist_model")


class Engine:
    def persist_model(self) -> None:
        pass


def make() -> Engine:
    return Engine()


X = getattr(make(), "persist_model")
