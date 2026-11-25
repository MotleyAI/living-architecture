from pkg.storage import StorageBackend


def load(s: StorageBackend) -> int:
    return s.load_model("m") + s.load_model(name="n") + s.load_model_sync(model_name="o")
