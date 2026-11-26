from pkg.storage import StorageBackend


def load(s: StorageBackend) -> int:
    return s.get_model("m") + s.get_model(name="n") + s.get_model_sync(model_name="o")
