class StorageBackend:
    def get_model(self, model_name: str) -> int:
        return len(model_name)

    def get_model_sync(self, model_name: str) -> int:
        return self.get_model(model_name)

    def save_model(self, model_name: str) -> None:
        print(model_name)
