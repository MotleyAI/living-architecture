from lib.store import Store


def f(store: Store) -> int:
    return store.load()


def load() -> int:
    return 0

x = Store().load()
