from pkg.store import StorageBackend, _ModelReadCache


def f(s: StorageBackend, c: _ModelReadCache) -> int:
    return s.get_model("a") + c.get_model("b")
