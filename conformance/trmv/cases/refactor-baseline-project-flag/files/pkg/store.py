class StorageBackend:
    def load(self, name: str) -> int:
        return len(name)


def use(s: StorageBackend) -> int:
    return len(3) + s.load("m") + len(1)


def other() -> int:
    return len(2)
