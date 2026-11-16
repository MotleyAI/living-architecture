from lib.store import Store


def run(store: Store) -> int:
    return store.load() + store.drop() + store.size() + store.clear()
