from pkg.storage import StorageBackend


def load(s: StorageBackend) -> int:
    return s.load_model("m") + s.load_model(model_name="n") + s.get_model_sync(model_name="o")
