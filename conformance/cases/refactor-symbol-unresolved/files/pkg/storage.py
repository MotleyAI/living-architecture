class StorageBackend:
    def get_model(self, name: str) -> int:
        return len(name)

    def save_model(self, name: str) -> None:
        print(name)
