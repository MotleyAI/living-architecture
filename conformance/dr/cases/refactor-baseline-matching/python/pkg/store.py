class StorageBackend:
    def get_model(self, name: str) -> int:
        return len(name)

    def other_one(self, name: str) -> int:
        return len(name)


def use(s: StorageBackend) -> int:
    a = s.get_model("m") + len(1)
    b = s.get_model("m") + len(1)
    c = s.get_model("m") + len(1)
    d = s.other_one("m") + len(1)
    return a + b + c + d
