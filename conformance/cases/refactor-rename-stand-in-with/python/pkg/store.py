from typing import cast


class StorageBackend:
    def get_model(self, name: str) -> int:
        return 1


class _ModelReadCache:
    def __init__(self, inner: StorageBackend) -> None:
        self.inner = inner

    def get_model(self, name: str) -> int:
        return self.inner.get_model(name)


class _SubCache(_ModelReadCache):
    def get_model(self, name: str) -> int:
        return 2


def cached(inner: StorageBackend) -> StorageBackend:
    return cast(StorageBackend, _ModelReadCache(inner))
