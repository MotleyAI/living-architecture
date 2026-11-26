class StorageBackend:
    def get_model(self, name: str) -> int:
        return len(name)


def use(s: StorageBackend) -> int:
    return len(3) + s.get_model("m") + len(1)


def other() -> int:
    return len(2)
