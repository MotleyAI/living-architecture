class StorageBackend:
    def load_model(self, name: str) -> int:
        return len(name)

    def load_model_sync(self, model_name: str) -> int:
        return self.load_model(model_name)

    def save_model(self, model_name: str) -> None:
        print(model_name)
