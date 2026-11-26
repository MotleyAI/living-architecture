class StorageBackend:
    def load(self, name: str) -> int:
        return len(name)

    def other_one(self, name: str) -> int:
        return len(name)


def use(s: StorageBackend) -> int:
    a = s.load("m") + len(1)
    b = s.load("m") + len(1)
    c = s.load("m") + len(1)
    d = s.other_one("m") + len(1)
    return a + b + c + d
